"""
Factor de Inversión Municipal (25% del Índice de Viabilidad) — Integrante 2.

Define la vista `v_factor_inversion`, que convierte los contratos ambientales
cargados desde SICOP en un puntaje 0-100 por cantón.

Es la capacidad demostrable de esta fuente: sin esto habría una tabla con
contratos, pero nada que el mapa pueda pintar.

A diferencia de `v_factor_ambiental` (Integrante 1), acá se usa una vista
NORMAL y no materializada. La razón es el costo: el factor ambiental cruza
geometrías 1:5mil de 84 cantones y tarda minutos, así que hay que guardarlo en
disco. Este factor son sumas y conteos sobre unos miles de filas sin geometría:
se calcula en milisegundos, y una vista normal tiene la ventaja de quedar al
día sola en cuanto el ETL inserta contratos nuevos, sin necesidad de refrescar.
"""
import os
import sys

# etl/common/db.py es compartido por las cuatro fuentes del proyecto y no es un
# paquete instalable, así que se agrega su carpeta al path.
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

from db import get_connection  # noqa: E402

# Los pesos internos y la forma de normalizar son una DECISIÓN DEL EQUIPO, no
# un estándar oficial. Hay que presentarlos como tales en la exposición: son
# una inferencia construida sobre los datos, no un dato en sí.
#
# Tres sub-puntajes, porque "inversión municipal ambiental" no es solo plata:
#
#   sub_monto      cuánta plata en contratos ambientales por habitante. Se
#                  divide por población para no premiar a los cantones grandes
#                  solo por ser grandes. Si el cantón no tiene población
#                  cargada, se cae al monto absoluto (queda documentado en la
#                  columna `base_monto` de la vista).
#   sub_cantidad   cuántos contratos ambientales distintos. Un cantón con un
#                  solo contrato gigante no demuestra el mismo compromiso
#                  sostenido que uno con varios.
#   sub_diversidad cuántas de las 6 categorías del clasificador aparecen. Un
#                  cantón que solo contrata recolección de basura invierte
#                  menos en ambiente que uno que además hace arborización y
#                  tratamiento de aguas.
#
# Los dos primeros se normalizan con PERCENT_RANK y no con min-max porque la
# distribución del gasto municipal tiene cola muy larga: un solo contrato de
# alcantarillado de miles de millones aplastaría la escala de los otros 83
# cantones.
#
# Un cantón sin ningún contrato ambiental queda en 0, no en NULL: la ausencia
# de inversión municipal ambiental es información, no un dato faltante.

SQL_FACTOR_INVERSION = """
-- `DROP ... IF EXISTS` solo ignora que el objeto NO exista; si existe pero es
-- de otro tipo, PostgreSQL aborta con "is not a materialized view". Como esta
-- vista pasó de materializada a normal durante el desarrollo, hay que mirar
-- primero qué es y borrarla con la sentencia que corresponde.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class
                WHERE relname = 'v_factor_inversion' AND relkind = 'm') THEN
        EXECUTE 'DROP MATERIALIZED VIEW v_factor_inversion CASCADE';
    ELSIF EXISTS (SELECT 1 FROM pg_class
                   WHERE relname = 'v_factor_inversion' AND relkind = 'v') THEN
        EXECUTE 'DROP VIEW v_factor_inversion CASCADE';
    END IF;
END $$;

CREATE VIEW v_factor_inversion AS
WITH agregado AS (
    SELECT
        c.canton_id,
        c.codigo_ine,
        c.nombre,
        c.provincia,
        c.poblacion,
        COUNT(ca.contrato_id)                                AS contratos,
        -- Solo colones: un contrato que quedó en dólares porque SICOP no trajo
        -- tipo de cambio no se puede sumar aquí sin mentir sobre el monto.
        COALESCE(SUM(ca.monto) FILTER (WHERE ca.moneda = 'CRC'), 0) AS monto_total,
        COUNT(ca.contrato_id) FILTER (WHERE ca.moneda <> 'CRC')     AS contratos_otra_moneda,
        COUNT(DISTINCT ca.categoria_detectada)               AS categorias
    FROM cantones c
    LEFT JOIN contratos_ambientales ca
           ON ca.canton_id = c.canton_id
          AND ca.fuente_id = (SELECT fuente_id FROM fuentes WHERE codigo = 'SICOP')
    GROUP BY c.canton_id, c.codigo_ine, c.nombre, c.provincia, c.poblacion
),

crudo AS (
    SELECT
        agregado.*,
        CASE WHEN poblacion IS NULL OR poblacion = 0
             THEN 'monto_absoluto'
             ELSE 'monto_por_habitante'
        END AS base_monto,
        CASE WHEN poblacion IS NULL OR poblacion = 0
             THEN monto_total
             ELSE monto_total / poblacion
        END AS monto_normalizable
    FROM agregado
),

puntajes AS (
    SELECT
        crudo.*,
        -- Los cantones sin contratos quedan fuera del ranking y se fuerzan a 0
        -- más abajo, para que no ocupen percentiles y desplacen a los que sí
        -- tienen inversión.
        PERCENT_RANK() OVER (ORDER BY monto_normalizable) * 100.0 AS sub_monto,
        PERCENT_RANK() OVER (ORDER BY contratos) * 100.0          AS sub_cantidad,
        LEAST(categorias / 6.0, 1.0) * 100.0                      AS sub_diversidad
    FROM crudo
)

SELECT
    canton_id,
    codigo_ine,
    nombre,
    provincia,
    contratos,
    contratos_otra_moneda,
    ROUND(monto_total::numeric, 2)         AS monto_total,
    categorias,
    base_monto,
    ROUND(sub_monto::numeric, 2)           AS sub_monto,
    ROUND(sub_cantidad::numeric, 2)        AS sub_cantidad,
    ROUND(sub_diversidad::numeric, 2)      AS sub_diversidad,
    -- Pesos internos del Factor de Inversión Municipal (decisión del equipo):
    -- el monto pesa más porque es lo que mide plata comprometida; la cantidad
    -- y la diversidad corrigen los casos de un solo contrato grande.
    CASE WHEN contratos = 0 THEN 0.00 ELSE
        ROUND((0.50 * sub_monto + 0.30 * sub_cantidad + 0.20 * sub_diversidad)::numeric, 2)
    END AS factor_inversion
FROM puntajes;

COMMENT ON VIEW v_factor_inversion IS
    'Factor de Inversion Municipal por canton a partir de contratos ambientales '
    'de SICOP (SV_CONT_0009 + SV_CONT_0014 + SV_CONT_0016). La clasificacion '
    'ambiental es por palabras clave y los pesos son decision del equipo, '
    'documentados en docs/sicop.md. No es un indicador oficial.';
"""


def _existe_factor_inversion(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('v_factor_inversion') IS NOT NULL")
        return cur.fetchone()[0]


def refrescar_factor_inversion():
    """
    Se deja por simetría con el ETL del SNIT y para que el orquestador no tenga
    que saber si el factor es vista o vista materializada.

    Como `v_factor_inversion` es una vista normal, no hay nada que refrescar:
    queda al día en cuanto la transacción de carga hace commit. Devuelve True
    si la vista existe, False si todavía hay que crearla con
    `--calcular-factor`.
    """
    with get_connection() as conn:
        return bool(_existe_factor_inversion(conn))


def calcular_factor_inversion(mostrar=10):
    """
    Crea (o recrea) la vista v_factor_inversion y muestra el ranking.
    Convierte los contratos de SICOP en un puntaje por cantón.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_FACTOR_INVERSION)
            cur.execute(
                """
                SELECT nombre, provincia, contratos, monto_total, categorias,
                       base_monto, factor_inversion
                  FROM v_factor_inversion
                 ORDER BY factor_inversion DESC, monto_total DESC
                """
            )
            filas = cur.fetchall()

    con_datos = [f for f in filas if f[2] > 0]
    print("\nFactor de Inversión Municipal por cantón (v_factor_inversion)")
    print(
        "{:<24} {:<12} {:>6} {:>16} {:>5} {:>8}".format(
            "cantón", "provincia", "contr", "monto", "cat", "factor"
        )
    )
    for fila in filas[:mostrar]:
        print(
            "{:<24} {:<12} {:>6} {:>16,.0f} {:>5} {:>8}".format(
                str(fila[0])[:24], str(fila[1])[:12], fila[2], float(fila[3]),
                fila[4], fila[6]
            )
        )
    print(
        "  ... ({} cantones en total, {} con al menos un contrato ambiental)".format(
            len(filas), len(con_datos)
        )
    )
    if filas and filas[0][5] == "monto_absoluto":
        print(
            "  nota: `cantones.poblacion` está vacía, así que sub_monto usa el "
            "monto absoluto. Cárguela para normalizar por habitante."
        )
    return len(filas)
