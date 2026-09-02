from fastapi import APIRouter, Depends
from psycopg2.extensions import cursor as Cursor

from app.database import get_db
from app.indice import calcular_y_guardar_indices

router = APIRouter(prefix="/indice-viabilidad", tags=["indice-viabilidad"])


@router.get("")
def listar_indices(cur: Cursor = Depends(get_db)):
    """Índice de viabilidad ya calculado por cantón, con los pesos usados."""
    cur.execute(
        """
        SELECT
            iv.canton_id, c.nombre AS nombre_canton,
            iv.factor_ambiental, iv.factor_inversion,
            iv.factor_conectividad, iv.factor_seguridad,
            iv.indice_total, iv.pesos_usados, iv.fecha_calculo
        FROM indice_viabilidad iv
        JOIN cantones c ON c.canton_id = iv.canton_id
        ORDER BY iv.indice_total DESC
        """
    )
    return cur.fetchall()


@router.post("/recalcular")
def recalcular(cur: Cursor = Depends(get_db)):
    """
    Recalcula el índice de todos los cantones a partir de los datos actuales
    de las cuatro fuentes. Se corre después de cada sincronización de ETL.
    """
    total = calcular_y_guardar_indices(cur)
    cur.connection.commit()
    return {"cantones_actualizados": total}
