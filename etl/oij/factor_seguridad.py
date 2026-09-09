"""
Factor de Seguridad (25% del Índice de Viabilidad) — Integrante 4.

Define la vista `v_factor_seguridad`, que convierte las estadísticas
policiales agregadas cargadas desde el OIJ en un puntaje 0-100 por cantón —
el mismo cálculo que antes vivía en `backend/app/indice.py::_factor_seguridad`,
movido acá para que esta fuente tenga un endpoint propio con desglose, igual
que `v_factor_ambiental` (SNIT), `v_factor_inversion` (SICOP) y
`v_factor_conectividad` (OSM).

Es una vista NORMAL, no materializada: es una suma sobre unos cientos de
filas sin cruce de geometrías, se calcula en milisegundos y queda al día
sola en cuanto el ETL inserta estadísticas nuevas.

Metodología (documentada porque es decisión del equipo, no un indicador
oficial): se suma la cantidad de incidentes de UN SOLO AÑO por cantón (ver
"Año de referencia" abajo — nunca de varios años mezclados), se calcula una
tasa por cada 10 000 habitantes cuando el cantón tiene `poblacion` cargada
(si no, se usa el total crudo de incidentes, igual que antes en Python), y
esa tasa se normaliza min-max contra los 84 cantones y se INVIERTE: a menor
tasa de incidencia, mayor Factor de Seguridad. Un cantón sin ninguna
estadística cargada (o solo con años ajenos al de referencia) queda con 0
delitos, no fuera del cálculo — ver el LEFT JOIN.

## Año de referencia (`OIJ_ANIO_REFERENCIA`)

Los recursos del OIJ pueden traer varios años juntos, y las estadísticas de
`estadisticas_seguridad` de distintos cantones pueden venir de corridas
distintas (`sync_oij.py` corrido varias veces con archivos de años
distintos). Sumar todo sin distinguir el año haría el factor incomparable
entre cantones —uno con datos de 2023 y 2024 juntos no es comparable con
uno que solo tiene 2024— y por eso la vista SIEMPRE filtra a un solo año:

1. Si la variable de entorno `OIJ_ANIO_REFERENCIA` está definida (en el
   `.env` de la raíz, ya viene declarada como decisión del equipo), se usa
   ese año, sin importar qué haya cargado en la tabla.
2. Si no está definida, y la tabla tiene datos de un único año, se usa ese
   año automáticamente (caso normal: una sola carga).
3. Si no está definida y la tabla tiene datos de DOS O MÁS años distintos,
   `calcular_factor_seguridad()` se niega a crear la vista y explica cómo
   resolverlo (fijar `OIJ_ANIO_REFERENCIA` o limpiar los años que sobran) —
   mezclarlos en silencio produciría un factor engañoso.
4. Si la tabla está vacía, no hace falta año: la vista queda en 50 para
   todos (ver más abajo), igual que antes.

CAMBIO respecto a la versión anterior en Python (documentarlo es justo lo
que pide el enunciado del curso): antes, `_factor_seguridad` calculaba esto
mismo en cada llamada a `/indice-viabilidad/recalcular`, directo sobre
`cantones`/`estadisticas_seguridad`, sumando TODOS los años cargados juntos
sin distinguir — sin depender de que existiera ninguna vista, y funcionaba
incluso sin haber corrido nunca el ETL del OIJ (todos los cantones quedaban
en 50, empatados, por falta de variación). Con la vista: (a) el cálculo
ahora exige un año de referencia único, por lo dicho arriba, y (b) si
todavía no existe la vista (nadie corrió `sync_oij.py --calcular-factor`),
el Factor de Seguridad queda en 0.0 para todos, no en 50 — igual criterio
que ya usan ambiental, inversión y conectividad cuando su vista no existe.
Una vez que la vista SÍ existe (aunque no haya ninguna fila para el año de
referencia todavía), el resultado sigue siendo 50 para todos, como antes.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

from dotenv import load_dotenv  # noqa: E402

from db import get_connection  # noqa: E402

load_dotenv()

_ANIO_REFERENCIA_ENV = os.environ.get("OIJ_ANIO_REFERENCIA", "").strip()
#: Año de referencia fijado por el equipo en el .env, o None si no está
#: definida — en ese caso se intenta deducir automáticamente (ver arriba).
ANIO_REFERENCIA: int | None = int(_ANIO_REFERENCIA_ENV) if _ANIO_REFERENCIA_ENV else None

# {filtro_anio} se rellena en tiempo de ejecución con "AND e.anio = 2024" (o
# similar) una vez resuelto el año — nunca queda como SUM sin filtrar.
SQL_FACTOR_SEGURIDAD = """
CREATE OR REPLACE VIEW v_factor_seguridad AS
WITH conteos AS (
    SELECT
        c.canton_id,
        c.codigo_ine,
        c.nombre,
        c.provincia,
        c.poblacion,
        COALESCE(SUM(e.cantidad), 0) AS total_delitos
    FROM cantones c
    -- LEFT JOIN, no INNER: un cantón sin estadísticas del año de referencia
    -- debe seguir apareciendo en el ranking con total_delitos = 0, no
    -- desaparecer de él (mismo criterio que v_factor_conectividad). El
    -- filtro de año va DENTRO del ON, no en un WHERE aparte, para no
    -- convertir el LEFT JOIN en un INNER JOIN de facto.
    LEFT JOIN estadisticas_seguridad e
           ON e.canton_id = c.canton_id
          {filtro_anio}
    GROUP BY c.canton_id, c.codigo_ine, c.nombre, c.provincia, c.poblacion
),
tasas AS (
    SELECT
        conteos.*,
        -- Delitos por 10,000 habitantes cuando hay población cargada; si no
        -- (o es 0), se usa el total crudo — mismo criterio que la versión
        -- en Python de indice.py (`if fila["poblacion"]:`).
        CASE
            WHEN poblacion IS NOT NULL AND poblacion > 0
                THEN total_delitos::numeric / poblacion * 10000
            ELSE total_delitos::numeric
        END AS tasa_incidencia
    FROM conteos
),
rango AS (
    SELECT MIN(tasa_incidencia) AS minimo, MAX(tasa_incidencia) AS maximo FROM tasas
)
SELECT
    t.canton_id,
    t.codigo_ine,
    t.nombre,
    t.provincia,
    t.poblacion,
    t.total_delitos,
    ROUND(t.tasa_incidencia, 4) AS tasa_incidencia,
    -- Min-max sobre los 84 cantones, INVERTIDO: a menor tasa, mayor
    -- puntaje de seguridad. Si todavía no hay ninguna variación (rango 0,
    -- típicamente porque no se ha cargado ninguna estadística), todos
    -- quedan en 50 en vez de dividir por cero.
    CASE
        WHEN rango.maximo = rango.minimo THEN 50.0
        ELSE ROUND(
            100 - (((t.tasa_incidencia - rango.minimo) / (rango.maximo - rango.minimo)) * 100),
            2
        )
    END AS factor_seguridad
FROM tasas t, rango;

COMMENT ON VIEW v_factor_seguridad IS
    'Factor de Seguridad por canton para el ano de referencia (ver '
    'OIJ_ANIO_REFERENCIA), inverso de la tasa de incidencia delictiva '
    '(OIJ), normalizada min-max contra los 84 cantones. Estadisticas '
    'agregadas por canton: nunca implican nada sobre las personas '
    'residentes. Decision del equipo, documentada en docs/oij.md. No es '
    'un indicador oficial.';
"""


def _existe_factor_seguridad(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('v_factor_seguridad') IS NOT NULL")
        return bool(cur.fetchone()[0])


def _anios_cargados(conn) -> list[int]:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT anio FROM estadisticas_seguridad ORDER BY anio")
        return [fila[0] for fila in cur.fetchall()]


def resolver_anio_referencia(conn) -> int | None:
    """
    Decide qué año usa la vista, con la prioridad documentada en el
    docstring del módulo. Lanza ValueError si hay años mezclados y nadie
    fijó `OIJ_ANIO_REFERENCIA` — mezclarlos en silencio sería un factor
    engañoso, no una decisión razonable por defecto.
    """
    if ANIO_REFERENCIA is not None:
        return ANIO_REFERENCIA

    anios = _anios_cargados(conn)
    if not anios:
        return None
    if len(anios) == 1:
        return anios[0]

    raise ValueError(
        f"estadisticas_seguridad tiene datos de {len(anios)} años distintos ({anios}) "
        "y OIJ_ANIO_REFERENCIA no está fijada en el .env. Sumarlos todos daría un "
        "Factor de Seguridad engañoso (un cantón con dos años cargados no sería "
        "comparable con uno que solo tiene uno). Fijá OIJ_ANIO_REFERENCIA=<año> en "
        "el .env de la raíz del repo con el año que el equipo decida usar, o borrá "
        "las filas de los años que no correspondan de estadisticas_seguridad."
    )


def refrescar_factor_seguridad() -> bool:
    """
    Se deja por simetría con SNIT/SICOP/OSM y para que el orquestador no
    tenga que saber si el factor es vista o vista materializada.

    Como `v_factor_seguridad` es una vista normal, no hay nada que
    refrescar: queda al día en cuanto la transacción de carga hace commit.
    Devuelve True si la vista existe, False si todavía hay que crearla con
    `--calcular-factor`.
    """
    with get_connection() as conn:
        return _existe_factor_seguridad(conn)


def calcular_factor_seguridad(mostrar: int = 10) -> int:
    """Crea (o recrea) la vista v_factor_seguridad y muestra el ranking."""
    with get_connection() as conn:
        anio = resolver_anio_referencia(conn)
        filtro_anio = f"AND e.anio = {anio}" if anio is not None else ""
        sql = SQL_FACTOR_SEGURIDAD.format(filtro_anio=filtro_anio)

        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(
                """
                SELECT nombre, provincia, total_delitos, tasa_incidencia, factor_seguridad
                  FROM v_factor_seguridad
                 ORDER BY factor_seguridad DESC, total_delitos ASC
                """
            )
            filas = cur.fetchall()

    con_datos = [f for f in filas if f[2] > 0]
    etiqueta_anio = f"año {anio}" if anio is not None else "sin datos cargados"
    print(f"\nFactor de Seguridad por cantón (v_factor_seguridad, {etiqueta_anio}) — mayor puntaje = menor incidencia relativa")
    print(
        "{:<24} {:<12} {:>10} {:>14} {:>8}".format(
            "cantón", "provincia", "delitos", "tasa/10k hab.", "factor"
        )
    )
    for fila in filas[:mostrar]:
        print(
            "{:<24} {:<12} {:>10} {:>14} {:>8}".format(
                str(fila[0])[:24], str(fila[1])[:12], fila[2], fila[3], fila[4]
            )
        )
    print(
        "  ... ({} cantones en total, {} con al menos un incidente del {})".format(
            len(filas), len(con_datos), etiqueta_anio
        )
    )
    return len(filas)
