"""
Factor de Conectividad (25% del Índice de Viabilidad) — Integrante 3.

Define la vista `v_factor_conectividad`, que convierte los puntos de interés
cargados desde OSM/Overpass en un puntaje 0-100 por cantón — el mismo cálculo
que antes vivía en `backend/app/indice.py::_factor_conectividad`, movido acá
para que esta fuente tenga un endpoint propio con desglose, igual que
`v_factor_ambiental` (SNIT, en `etl/snit/factor_ambiental.py`) y
`v_factor_inversion` (SICOP, en `etl/sicop/factor_inversion.py`).

Es una vista NORMAL, no materializada: como `v_factor_inversion`, es una
cuenta sobre unos cientos de filas sin cruce de geometrías (el `canton_id` de
cada POI ya viene resuelto desde la carga, no hay que intersectar nada acá),
se calcula en milisegundos, y queda al día sola en cuanto el ETL inserta o
vence POIs, sin necesidad de refrescar.

CAMBIO respecto a la versión anterior en Python (documentarlo es justo lo que
pide el enunciado del curso: decisión del equipo, no dato oficial): antes,
`_normalizar_min_max` solo recibía los cantones con AL MENOS un POI —un
cantón sin ninguno quedaba fuera del cálculo de mínimo/máximo y se forzaba a
0 después, en `calcular_y_guardar_indices`. Acá el mínimo/máximo se calcula
sobre los 84 cantones —con y sin datos, vía LEFT JOIN—, que es la lectura más
directa de "normalizado contra el resto del país": evita que un cantón con
muy poca infraestructura empate en 0 con uno que no tiene nada. Esto puede
mover el número de algún cantón con pocos POIs respecto a la versión anterior
del índice — no es un bug, es una normalización más completa.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

from db import get_connection  # noqa: E402

SQL_FACTOR_CONECTIVIDAD = """
CREATE OR REPLACE VIEW v_factor_conectividad AS
WITH conteos AS (
    SELECT
        c.canton_id,
        c.codigo_ine,
        c.nombre,
        c.provincia,
        COUNT(o.poi_id) FILTER (WHERE o.categoria = 'centro_acopio') AS pois_centro_acopio,
        COUNT(o.poi_id) FILTER (WHERE o.categoria = 'escuela')       AS pois_escuela,
        COUNT(o.poi_id) FILTER (WHERE o.categoria = 'via_principal') AS pois_via_principal,
        COUNT(o.poi_id)                                              AS total_pois
    FROM cantones c
    -- LEFT JOIN, no INNER: un cantón sin ningún POI vigente debe seguir
    -- apareciendo en el ranking con total_pois = 0, no desaparecer de él.
    LEFT JOIN infraestructura_osm o
           ON o.canton_id = c.canton_id
          AND o.valido_hasta > now()
    GROUP BY c.canton_id, c.codigo_ine, c.nombre, c.provincia
),
rango AS (
    SELECT MIN(total_pois) AS minimo, MAX(total_pois) AS maximo FROM conteos
)
SELECT
    conteos.canton_id,
    conteos.codigo_ine,
    conteos.nombre,
    conteos.provincia,
    conteos.pois_centro_acopio,
    conteos.pois_escuela,
    conteos.pois_via_principal,
    conteos.total_pois,
    -- Min-max sobre los 84 cantones. Si todavía nadie tiene POIs cargados
    -- (rango 0), todos quedan en 50 en vez de dividir por cero — mismo
    -- criterio que usa v_factor_seguridad (OIJ) para la misma situación.
    CASE
        WHEN rango.maximo = rango.minimo THEN 50.0
        ELSE ROUND(
            ((conteos.total_pois - rango.minimo)::numeric / (rango.maximo - rango.minimo)) * 100,
            2
        )
    END AS factor_conectividad
FROM conteos, rango;

COMMENT ON VIEW v_factor_conectividad IS
    'Factor de Conectividad por canton a partir de puntos de interes vigentes '
    'de OSM/Overpass (centro_acopio, escuela, via_principal). Normalizado '
    'min-max contra los 84 cantones, con y sin datos. Decision del equipo, '
    'documentada en docs/osm.md. No es un indicador oficial.';
"""


def _existe_factor_conectividad(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('v_factor_conectividad') IS NOT NULL")
        return bool(cur.fetchone()[0])


def refrescar_factor_conectividad() -> bool:
    """
    Se deja por simetría con SNIT/SICOP y para que el orquestador no tenga
    que saber si el factor es vista o vista materializada.

    Como `v_factor_conectividad` es una vista normal, no hay nada que
    refrescar: queda al día en cuanto la transacción de carga hace commit.
    Devuelve True si la vista existe, False si todavía hay que crearla con
    `--calcular-factor`.
    """
    with get_connection() as conn:
        return _existe_factor_conectividad(conn)


def calcular_factor_conectividad(mostrar: int = 10) -> int:
    """Crea (o recrea) la vista v_factor_conectividad y muestra el ranking."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_FACTOR_CONECTIVIDAD)
            cur.execute(
                """
                SELECT nombre, provincia, pois_centro_acopio, pois_escuela,
                       pois_via_principal, total_pois, factor_conectividad
                  FROM v_factor_conectividad
                 ORDER BY factor_conectividad DESC, total_pois DESC
                """
            )
            filas = cur.fetchall()

    con_datos = [f for f in filas if f[5] > 0]
    print("\nFactor de Conectividad por cantón (v_factor_conectividad)")
    print(
        "{:<24} {:<12} {:>7} {:>8} {:>6} {:>6} {:>8}".format(
            "cantón", "provincia", "acopio", "escuela", "vía", "total", "factor"
        )
    )
    for fila in filas[:mostrar]:
        print(
            "{:<24} {:<12} {:>7} {:>8} {:>6} {:>6} {:>8}".format(
                str(fila[0])[:24], str(fila[1])[:12], fila[2], fila[3], fila[4], fila[5], fila[6]
            )
        )
    print(
        "  ... ({} cantones en total, {} con al menos un punto de interés vigente)".format(
            len(filas), len(con_datos)
        )
    )
    return len(filas)
