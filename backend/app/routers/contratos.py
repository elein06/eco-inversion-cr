from fastapi import APIRouter, Depends, Query
from psycopg2.extensions import cursor as Cursor

from app.database import get_db

router = APIRouter(prefix="/contratos-ambientales", tags=["contratos-ambientales"])


@router.get("")
def listar_contratos(
    canton_id: int | None = Query(default=None),
    cur: Cursor = Depends(get_db),
):
    """Contratos SICOP clasificados como ambientales (fuente: Integrante 2)."""
    if canton_id is not None:
        cur.execute(
            """
            SELECT * FROM contratos_ambientales
            WHERE canton_id = %s
            ORDER BY fecha_contrato DESC NULLS LAST
            """,
            (canton_id,),
        )
    else:
        cur.execute(
            "SELECT * FROM contratos_ambientales ORDER BY fecha_contrato DESC NULLS LAST LIMIT 500"
        )
    return cur.fetchall()
