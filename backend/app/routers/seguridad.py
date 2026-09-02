from fastapi import APIRouter, Depends, Query
from psycopg2.extensions import cursor as Cursor

from app.database import get_db

router = APIRouter(prefix="/seguridad", tags=["seguridad"])

ADVERTENCIA = (
    "Estadísticas agregadas por cantón (Poder Judicial / OIJ). No representan "
    "ni implican nada sobre las personas residentes de un cantón."
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
