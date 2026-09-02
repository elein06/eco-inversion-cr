from fastapi import APIRouter, Depends, Query
from psycopg2.extensions import cursor as Cursor

from app.database import get_db

router = APIRouter(prefix="/infraestructura", tags=["infraestructura"])


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
