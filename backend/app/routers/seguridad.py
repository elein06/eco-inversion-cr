"""
Router de la fuente OIJ / Poder Judicial — Integrante 4.

Expone las estadísticas crudas (como antes), y el Factor de Seguridad por
cantón con su desglose. Es el equivalente de lo que `ambiental.py` hace con
el SNIT, `inversion.py` con SICOP e `infraestructura.py` con OSM: el
frontend nunca calcula nada, solo habla con estos endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extensions import cursor as Cursor

from app.database import get_db

router = APIRouter(prefix="/seguridad", tags=["seguridad (OIJ)"])

ADVERTENCIA = (
    "Estadísticas agregadas por cantón (Poder Judicial / OIJ). No representan "
    "ni implican nada sobre las personas residentes de un cantón. Su relación "
    "con el índice de viabilidad es una correlación definida por el equipo, "
    "no una causalidad."
)

# Columnas de v_factor_seguridad que se devuelven. Explícitas, no SELECT *,
# para que un cambio en la vista no altere en silencio el contrato de la
# API — mismo criterio que COLUMNAS_FACTOR en inversion.py/infraestructura.py.
COLUMNAS_FACTOR = """
    canton_id, codigo_ine, nombre, provincia, poblacion,
    total_delitos, tasa_incidencia, factor_seguridad
"""


def _exigir_vista(cur: Cursor) -> None:
    """
    La vista la crea el ETL con `sync_oij.py --calcular-factor`, no el
    esquema. Si todavía no existe, consultarla lanzaría un UndefinedTable
    que llega al frontend como un 500 sin explicación. Se prefiere un 503
    que diga qué falta correr — mismo criterio que `/inversion/factor` y
    `/infraestructura/factor`.
    """
    cur.execute("SELECT to_regclass('v_factor_seguridad') IS NOT NULL AS existe")
    if not cur.fetchone()["existe"]:
        raise HTTPException(
            status_code=503,
            detail=(
                "La vista v_factor_seguridad no existe todavía. Corra el ETL del "
                "OIJ: cd etl/oij && python sync_oij.py --calcular-factor"
            ),
        )


@router.get("")
def listar_estadisticas(
    canton_id: int | None = Query(default=None),
    anio: int | None = Query(default=None),
    cur: Cursor = Depends(get_db),
):
    """Estadísticas policiales agregadas por cantón/año (fuente: Integrante 4 — OIJ)."""
    condiciones = []
    parametros: list = []

    if canton_id is not None:
        condiciones.append("canton_id = %s")
        parametros.append(canton_id)
    if anio is not None:
        condiciones.append("anio = %s")
        parametros.append(anio)

    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    cur.execute(
        f"""
        SELECT estadistica_id, canton_id, tipo_delito, cantidad, anio, fecha_consulta
        FROM estadisticas_seguridad
        {where}
        ORDER BY anio DESC, cantidad DESC
        """,
        parametros,
    )
    return {"advertencia": ADVERTENCIA, "datos": cur.fetchall()}


@router.get("/factor")
def listar_factor_seguridad(
    cur: Cursor = Depends(get_db),
    canton: str | None = Query(None, description="Nombre del cantón, ej. San José"),
    provincia: str | None = Query(None, description="Nombre de la provincia"),
    solo_con_datos: bool = Query(
        False, description="Deja fuera los cantones sin ninguna estadística cargada"
    ),
):
    """
    Factor de Seguridad por cantón, con el desglose que lo forma.

    Sale de la vista v_factor_seguridad, que crea el ETL del OIJ. Es el
    inverso de la tasa de incidencia delictiva (por 10 000 habitantes),
    normalizado min-max contra los 84 cantones (con y sin datos): 100 el que
    tiene menor incidencia relativa, 0 el que tiene mayor. El detalle está
    en docs/oij.md — es una decisión del equipo, no un indicador oficial.

    Un cantón sin ninguna estadística cargada queda con `total_delitos = 0`,
    no ausente del listado — la falta de datos no es lo mismo que ausencia
    de delitos, pero tratarlo así (en vez de excluirlo) es una decisión
    documentada, igual que en /infraestructura/factor.
    """
    _exigir_vista(cur)

    condiciones = []
    parametros: list = []

    if canton:
        condiciones.append("unaccent(lower(nombre)) = unaccent(lower(%s))")
        parametros.append(canton)

    if provincia:
        condiciones.append("unaccent(lower(provincia)) = unaccent(lower(%s))")
        parametros.append(provincia)

    if solo_con_datos:
        condiciones.append("total_delitos > 0")

    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""

    cur.execute(
        """
        SELECT {}
        FROM v_factor_seguridad
        {}
        ORDER BY factor_seguridad DESC, total_delitos ASC
        """.format(COLUMNAS_FACTOR, where),
        parametros,
    )
    return {"advertencia": ADVERTENCIA, "datos": cur.fetchall()}


@router.get("/resumen")
def resumen_seguridad(cur: Cursor = Depends(get_db)):
    """
    Totales por tipo de delito y año, entre todos los cantones. Sirve para
    que la interfaz muestre la procedencia de los datos, igual que
    /ambiental/capas/resumen (SNIT), /inversion/resumen (SICOP) e
    /infraestructura/resumen (OSM).

    No depende de la vista: lee la tabla directamente, así que responde
    aunque todavía no se haya corrido --calcular-factor.
    """
    cur.execute(
        """
        SELECT
            tipo_delito,
            anio,
            SUM(cantidad) AS total,
            COUNT(DISTINCT canton_id) AS cantones,
            MAX(fecha_consulta) AS ultima_consulta
        FROM estadisticas_seguridad
        GROUP BY tipo_delito, anio
        ORDER BY anio DESC, total DESC
        """
    )
    return {"advertencia": ADVERTENCIA, "datos": cur.fetchall()}


@router.get("/factor/{canton_id}")
def obtener_factor_seguridad(canton_id: int, cur: Cursor = Depends(get_db)):
    """Factor de Seguridad de un solo cantón, por su id."""
    _exigir_vista(cur)

    cur.execute(
        """
        SELECT {}
        FROM v_factor_seguridad
        WHERE canton_id = %s
        """.format(COLUMNAS_FACTOR),
        (canton_id,),
    )
    fila = cur.fetchone()
    if fila is None:
        raise HTTPException(status_code=404, detail="Cantón no encontrado")
    return {"advertencia": ADVERTENCIA, "datos": fila}
