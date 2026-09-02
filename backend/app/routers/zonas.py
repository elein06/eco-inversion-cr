from fastapi import APIRouter, Depends
from psycopg2.extensions import cursor as Cursor

from app.database import get_db

router = APIRouter(prefix="/zonas", tags=["zonas"])


@router.get("")
def listar_zonas(cur: Cursor = Depends(get_db)):
    """Cantones con su geometría en GeoJSON — capa base del mapa."""
    cur.execute(
        """
        SELECT
            canton_id, codigo_ine, nombre, provincia, poblacion,
            ST_AsGeoJSON(geom)::json AS geom
        FROM cantones
        ORDER BY nombre
        """
    )
    return cur.fetchall()


@router.get("/{canton_id}")
def obtener_zona(canton_id: int, cur: Cursor = Depends(get_db)):
    cur.execute(
        """
        SELECT
            canton_id, codigo_ine, nombre, provincia, poblacion,
            ST_AsGeoJSON(geom)::json AS geom
        FROM cantones
        WHERE canton_id = %s
        """,
        (canton_id,),
    )
    return cur.fetchone()
