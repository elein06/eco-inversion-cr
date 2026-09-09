"""
Router de la fuente OSM/Overpass — Integrante 3.

Expone los POIs crudos (como antes), y el Factor de Conectividad por cantón
con su desglose por categoría. Es el equivalente de lo que `ambiental.py`
hace con el SNIT e `inversion.py` con SICOP: el frontend nunca habla con
Overpass, solo con estos endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extensions import cursor as Cursor

from app.database import get_db

router = APIRouter(prefix="/infraestructura", tags=["infraestructura (OSM)"])

# Columnas de v_factor_conectividad que se devuelven. Se listan explícitas y
# no con SELECT * para que un cambio en la vista no altere en silencio el
# contrato de la API — mismo criterio que COLUMNAS_FACTOR en inversion.py.
COLUMNAS_FACTOR = """
    canton_id, codigo_ine, nombre, provincia,
    pois_centro_acopio, pois_escuela, pois_via_principal, total_pois,
    factor_conectividad
"""


def _exigir_vista(cur: Cursor) -> None:
    """
    La vista la crea el ETL con `sync_osm.py --calcular-factor` (o al final
    de `cargar_todos_los_cantones.py --calcular-factor`), no el esquema. Si
    todavía no existe, consultarla lanzaría un UndefinedTable que llega al
    frontend como un 500 sin explicación. Se prefiere un 503 que diga qué
    falta correr — mismo criterio que `/inversion/factor`.
    """
    cur.execute("SELECT to_regclass('v_factor_conectividad') IS NOT NULL AS existe")
    if not cur.fetchone()["existe"]:
        raise HTTPException(
            status_code=503,
            detail=(
                "La vista v_factor_conectividad no existe todavía. Corra el ETL de "
                "OSM: cd etl/osm && python sync_osm.py --calcular-factor"
            ),
        )


@router.get("")
def listar_infraestructura(
    canton_id: int | None = Query(default=None),
    solo_vigente: bool = Query(default=True, description="Filtra por caché de 7 días de Overpass"),
    cur: Cursor = Depends(get_db),
):
    """POIs de OpenStreetMap/Overpass (fuente: Integrante 3), con caché de 7 días."""
    condiciones = []
    parametros: list = []

    if canton_id is not None:
        condiciones.append("canton_id = %s")
        parametros.append(canton_id)
    if solo_vigente:
        condiciones.append("valido_hasta > now()")

    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    cur.execute(
        f"""
        SELECT
            poi_id, canton_id, categoria, nombre,
            ST_AsGeoJSON(geom)::json AS geom,
            fecha_consulta, valido_hasta
        FROM infraestructura_osm
        {where}
        ORDER BY fecha_consulta DESC
        LIMIT 1000
        """,
        parametros,
    )
    return cur.fetchall()


@router.get("/factor")
def listar_factor_conectividad(
    cur: Cursor = Depends(get_db),
    canton: str | None = Query(None, description="Nombre del cantón, ej. San José"),
    provincia: str | None = Query(None, description="Nombre de la provincia"),
    solo_con_pois: bool = Query(
        False, description="Deja fuera los cantones sin ningún punto de interés vigente"
    ),
):
    """
    Factor de Conectividad por cantón, con el desglose por categoría de POI.

    Sale de la vista v_factor_conectividad, que crea el ETL de OSM. Está
    normalizado min-max contra los 84 cantones (con y sin datos): 100 el que
    más puntos de interés vigentes tiene, 0 el que menos (o ninguno). El
    detalle está en docs/osm.md — es una decisión del equipo, no un
    indicador oficial.

    Un cantón sin ningún POI vigente queda en `total_pois = 0`, no ausente
    del listado: la falta de infraestructura mapeada es información, no un
    dato faltante. Por eso el filtro `solo_con_pois` es opcional y viene
    apagado.
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

    if solo_con_pois:
        condiciones.append("total_pois > 0")

    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""

    cur.execute(
        """
        SELECT {}
        FROM v_factor_conectividad
        {}
        ORDER BY factor_conectividad DESC, total_pois DESC
        """.format(COLUMNAS_FACTOR, where),
        parametros,
    )
    return cur.fetchall()


@router.get("/resumen")
def resumen_infraestructura(cur: Cursor = Depends(get_db)):
    """
    Cuántos POIs vigentes hay por categoría. Sirve para que la interfaz
    muestre la procedencia de los datos, igual que /ambiental/capas/resumen
    (SNIT) y /inversion/resumen (SICOP).

    No depende de la vista: lee la tabla directamente, así que responde
    aunque todavía no se haya corrido --calcular-factor.
    """
    cur.execute(
        """
        SELECT
            categoria,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE canton_id IS NULL) AS sin_canton,
            MAX(fecha_consulta) AS ultima_consulta
        FROM infraestructura_osm
        WHERE valido_hasta > now()
        GROUP BY categoria
        ORDER BY total DESC
        """
    )
    return cur.fetchall()


@router.get("/factor/{canton_id}")
def obtener_factor_conectividad(canton_id: int, cur: Cursor = Depends(get_db)):
    """Factor de Conectividad de un solo cantón, por su id."""
    _exigir_vista(cur)

    cur.execute(
        """
        SELECT {}
        FROM v_factor_conectividad
        WHERE canton_id = %s
        """.format(COLUMNAS_FACTOR),
        (canton_id,),
    )
    fila = cur.fetchone()
    if fila is None:
        raise HTTPException(status_code=404, detail="Cantón no encontrado")
    return fila
