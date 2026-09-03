"""
Factor Ambiental (25% del Indice de Viabilidad) — Integrante 1.

Define la vista materializada `v_factor_ambiental`, que convierte las tres
capas del SNIT en un puntaje por canton, y la mantiene al dia.

Es la capacidad demostrable de esta fuente: sin esto habria datos cargados
pero nada que mostrar en el mapa.
"""
import os
import sys
import time

# etl/common/db.py es compartido por las cuatro fuentes del proyecto y no es
# un paquete instalable, asi que se agrega su carpeta al path.
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

from db import get_connection  # noqa: E402

# Define la vista `v_factor_ambiental`, que el backend consume para llenar
# `indice_viabilidad.factor_ambiental`. Es una vista y no una tabla para no
# tocar el esquema compartido de db/schema.sql: cada vez que el ETL recarga las
# capas del SNIT, la vista queda al día sola.
#
# Todas las áreas y longitudes se calculan reproyectando a EPSG:5367
# (CR05 / CRTM05), que está en metros. Medirlas en EPSG:4326 daría grados
# cuadrados, que no son una unidad de superficie.
#
# Los umbrales y pesos son una DECISIÓN DEL EQUIPO, no un estándar oficial.
# Hay que presentarlos como tales en la exposición: son una inferencia
# construida sobre los datos, no un dato en sí.
#
# Es una vista MATERIALIZADA, no una vista normal: el cruce espacial de los 84
# cantones a escala 1:5mil contra 6 656 geometrías tarda varios minutos. Una
# vista común lo recalcularía en cada consulta y la API quedaría colgada cada
# vez que el frontend pinta el mapa. Materializada se calcula una sola vez, se
# guarda en disco y responde en milisegundos; se refresca al final de cada
# sincronización del SNIT, que corre una vez o semanalmente.

SQL_FACTOR_AMBIENTAL = """
DROP VIEW IF EXISTS v_factor_ambiental CASCADE;
DROP MATERIALIZED VIEW IF EXISTS v_factor_ambiental CASCADE;

CREATE MATERIALIZED VIEW v_factor_ambiental AS
WITH canton_m AS (
    SELECT
        canton_id,
        codigo_ine,
        nombre,
        provincia,
        ST_MakeValid(ST_Transform(geom, 5367)) AS geom_m,
        ST_Area(ST_MakeValid(ST_Transform(geom, 5367))) AS area_m2
    FROM cantones
),

-- Superficie del cantón cubierta por Áreas Silvestres Protegidas terrestres.
-- Se excluyen las áreas marinas: el índice orienta proyectos en tierra, y una
-- ASP marina frente a la costa no restringe el territorio del cantón.
-- Se unen las geometrías antes de medir, para no contar dos veces los
-- traslapes entre ASP.
asp AS (
    SELECT
        c.canton_id,
        COALESCE(
            ST_Area(ST_Union(ST_Intersection(c.geom_m,
                             ST_MakeValid(ST_Transform(s.geom, 5367))))),
            0
        ) AS area_asp_m2
    FROM canton_m c
    LEFT JOIN capas_snit s
           ON s.tipo_capa = 'area_protegida'
          AND s.atributos ->> 'descripcio' NOT IN
              ('Area marina protegida', 'Area Marina de Manejo')
          AND ST_Intersects(c.geom_m, ST_MakeValid(ST_Transform(s.geom, 5367)))
    GROUP BY c.canton_id
),

-- Superficie del cantón dentro de un corredor biológico.
corredor AS (
    SELECT
        c.canton_id,
        COALESCE(
            ST_Area(ST_Union(ST_Intersection(c.geom_m,
                             ST_MakeValid(ST_Transform(s.geom, 5367))))),
            0
        ) AS area_cb_m2
    FROM canton_m c
    LEFT JOIN capas_snit s
           ON s.tipo_capa = 'corredor_biologico'
          AND ST_Intersects(c.geom_m, ST_MakeValid(ST_Transform(s.geom, 5367)))
    GROUP BY c.canton_id
),

-- Longitud de red de drenaje dentro del cantón, en metros.
hidro AS (
    SELECT
        c.canton_id,
        COALESCE(
            SUM(ST_Length(ST_Intersection(c.geom_m,
                          ST_MakeValid(ST_Transform(s.geom, 5367))))),
            0
        ) AS largo_rios_m
    FROM canton_m c
    LEFT JOIN capas_snit s
           ON s.tipo_capa = 'hidrografia'
          AND ST_Intersects(c.geom_m, ST_MakeValid(ST_Transform(s.geom, 5367)))
    GROUP BY c.canton_id
),

crudo AS (
    SELECT
        c.canton_id,
        c.codigo_ine,
        c.nombre,
        c.provincia,
        c.area_m2 / 1000000.0                  AS area_km2,
        a.area_asp_m2 / NULLIF(c.area_m2, 0)   AS pct_asp,
        cb.area_cb_m2 / NULLIF(c.area_m2, 0)   AS pct_corredor,
        (h.largo_rios_m / 1000.0)
            / NULLIF(c.area_m2 / 1000000.0, 0) AS densidad_drenaje_km_km2
    FROM canton_m c
    JOIN asp      a  USING (canton_id)
    JOIN corredor cb USING (canton_id)
    JOIN hidro    h  USING (canton_id)
),

puntajes AS (
    SELECT
        crudo.*,

        -- Sub-puntaje ASP: banda, no binario.
        -- Un cantón sin nada protegido no ofrece el entorno natural que busca
        -- un proyecto de ecoturismo; uno casi enteramente protegido casi no
        -- deja terreno donde instalarse legalmente. El óptimo está en medio:
        -- entre 5% y 30% del territorio bajo protección.
        CASE
            WHEN pct_asp IS NULL  THEN 40.0
            WHEN pct_asp < 0.05   THEN 40.0 + (pct_asp / 0.05) * 60.0
            WHEN pct_asp <= 0.30  THEN 100.0
            ELSE GREATEST(40.0, 100.0 - ((pct_asp - 0.30) / 0.70) * 60.0)
        END AS sub_asp,

        -- Sub-puntaje corredor biológico: más cobertura suma, con techo en 30%.
        -- Pasado ese punto el aporte deja de diferenciar cantones.
        LEAST(COALESCE(pct_corredor, 0) / 0.30, 1.0) * 100.0 AS sub_corredor,

        -- Sub-puntaje hidrografía: densidad de drenaje relativa al resto del
        -- país. Se usa percentil y no min-max porque la distribución tiene cola
        -- larga y unos pocos cantones aplastarían la escala.
        PERCENT_RANK() OVER (ORDER BY densidad_drenaje_km_km2) * 100.0 AS sub_hidro
    FROM crudo
)

SELECT
    canton_id,
    codigo_ine,
    nombre,
    provincia,
    ROUND(area_km2::numeric, 2)                AS area_km2,
    ROUND((pct_asp * 100)::numeric, 2)         AS pct_area_protegida,
    ROUND((pct_corredor * 100)::numeric, 2)    AS pct_corredor_biologico,
    ROUND(densidad_drenaje_km_km2::numeric, 3) AS densidad_drenaje_km_km2,
    ROUND(sub_asp::numeric, 2)                 AS sub_asp,
    ROUND(sub_corredor::numeric, 2)            AS sub_corredor,
    ROUND(sub_hidro::numeric, 2)               AS sub_hidro,
    -- Pesos internos del Factor Ambiental (decisión del equipo):
    -- la restricción legal de las ASP pesa más que el resto, porque es la que
    -- determina si un proyecto se puede instalar del todo.
    ROUND((0.50 * sub_asp + 0.30 * sub_corredor + 0.20 * sub_hidro)::numeric, 2)
        AS factor_ambiental
FROM puntajes;

-- Índice único sobre canton_id: además de acelerar el JOIN del backend, es lo
-- que permite refrescar con CONCURRENTLY, sin bloquear a quien esté leyendo.
CREATE UNIQUE INDEX idx_v_factor_ambiental_canton
    ON v_factor_ambiental (canton_id);

COMMENT ON MATERIALIZED VIEW v_factor_ambiental IS
    'Factor Ambiental por cantón a partir de capas WFS del SNIT (ASP terrestres, '
    'corredores biológicos, red de drenaje). Pesos y umbrales son decisión del '
    'equipo, documentados en docs/snit.md. No es un indicador oficial.';
"""


def _existe_factor_ambiental(conn):
    """True si la vista materializada ya está creada."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('v_factor_ambiental') IS NOT NULL")
        return cur.fetchone()[0]


def refrescar_factor_ambiental():
    """
    Recalcula la vista materializada tras recargar las capas del SNIT. Si
    todavía no existe, no hace nada: la crea `--calcular-factor`.
    """
    with get_connection() as conn:
        if not _existe_factor_ambiental(conn):
            return False
        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY v_factor_ambiental")
    return True


def calcular_factor_ambiental():
    """
    Crea la vista materializada v_factor_ambiental y muestra el ranking.
    Es la capacidad demostrable de esta fuente: convierte tres capas del SNIT
    en un puntaje por cantón.
    """
    inicio = time.time()
    print("\nCalculando el Factor Ambiental en PostGIS. Tarda varios minutos:")
    print("  cruza 84 cantones a escala 1:5mil contra 6 656 geometrías.")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_FACTOR_AMBIENTAL)
            cur.execute(
                """
                SELECT nombre, provincia, pct_area_protegida,
                       pct_corredor_biologico, densidad_drenaje_km_km2,
                       factor_ambiental
                  FROM v_factor_ambiental
                 ORDER BY factor_ambiental DESC
                """
            )
            filas = cur.fetchall()

    print(
        "\nFactor Ambiental por cantón (v_factor_ambiental, "
        "calculada en {:.0f} s)".format(time.time() - inicio)
    )
    print(
        "{:<24} {:<12} {:>7} {:>7} {:>9} {:>8}".format(
            "cantón", "provincia", "%ASP", "%CB", "drenaje", "factor"
        )
    )
    for fila in filas[:10]:
        print(
            "{:<24} {:<12} {:>7} {:>7} {:>9} {:>8}".format(
                fila[0][:24], fila[1][:12], *fila[2:]
            )
        )
    print("  ... ({} cantones en total)".format(len(filas)))
    return len(filas)


# ------------------------------------------------------------------
