from fastapi import APIRouter, Depends, Request
from psycopg2.extensions import cursor as Cursor

from app import eventos
from app.auth import UsuarioSesion, requiere_admin
from app.database import get_db
from app.indice import calcular_y_guardar_indices

router = APIRouter(prefix="/indice-viabilidad", tags=["indice-viabilidad"])


@router.get("")
def listar_indices(cur: Cursor = Depends(get_db)):
    """Índice de viabilidad ya calculado por cantón, con los pesos usados. Público."""
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
def recalcular(
    request: Request,
    admin: UsuarioSesion = Depends(requiere_admin),
    cur: Cursor = Depends(get_db),
):
    """
    Flujo crítico F2 — Recalcula el índice oficial de todos los cantones a
    partir de los datos actuales de las cuatro fuentes. Solo administradores:
    el índice es lo que ven los inversionistas, así que cambiarlo es una
    operación de integridad. Se corre después de cada sincronización de ETL.
    """
    total = calcular_y_guardar_indices(cur)
    cur.connection.commit()
    eventos.registrar(
        "recalcular_indice",
        "exito",
        request=request,
        usuario_id=admin.usuario_id,
        cantones_actualizados=total,
    )
    return {"cantones_actualizados": total}
