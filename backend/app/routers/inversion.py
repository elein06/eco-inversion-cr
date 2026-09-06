"""
Router de la fuente SICOP — Integrante 2.

Expone el Factor de Inversión Municipal por cantón con su desglose, y el
resumen de los contratos ambientales que lo alimentan.

Es el equivalente de lo que `ambiental.py` hace con el SNIT. `contratos.py` ya
devuelve los contratos uno por uno; lo que faltaba era el puntaje y sus
sub-puntajes, que hasta ahora solo salían mezclados dentro de
`/indice-viabilidad` como un número suelto, sin nada que lo explique.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extensions import cursor as Cursor

from app.database import get_db

router = APIRouter(prefix="/inversion", tags=["inversión (SICOP)"])

# Columnas de v_factor_inversion que se devuelven. Se listan explícitas y no con
# SELECT * para que un cambio en la vista no altere en silencio el contrato de
# la API.
COLUMNAS_FACTOR = """
    canton_id, codigo_ine, nombre, provincia,
    contratos, contratos_otra_moneda, monto_total, categorias,
    base_monto,
    sub_monto, sub_cantidad, sub_diversidad,
    factor_inversion
"""


def _exigir_vista(cur: Cursor) -> None:
    """
    La vista la crea el ETL con `sync_sicop.py --calcular-factor`, no el
    esquema. Si todavía no existe, consultarla lanzaría un UndefinedTable que
    llega al frontend como un 500 sin explicación. Se prefiere un 503 que diga
    qué falta correr.
    """
    cur.execute("SELECT to_regclass('v_factor_inversion') IS NOT NULL AS existe")
    if not cur.fetchone()["existe"]:
        raise HTTPException(
            status_code=503,
            detail=(
                "La vista v_factor_inversion no existe todavía. Corra el ETL de "
                "SICOP: cd etl/sicop && python sync_sicop.py --calcular-factor"
            ),
        )


@router.get("/factor")
def listar_factor_inversion(
    cur: Cursor = Depends(get_db),
    canton: str | None = Query(None, description="Nombre del cantón, ej. Turrialba"),
    provincia: str | None = Query(None, description="Nombre de la provincia"),
    solo_con_contratos: bool = Query(
        False,
        description="Deja fuera los cantones sin ningún contrato ambiental",
    ),
):
    """
    Factor de Inversión Municipal por cantón, con el desglose de sus tres
    sub-puntajes.

    Sale de la vista v_factor_inversion, que crea el ETL de SICOP. Los pesos
    internos (50% monto, 30% cantidad, 20% diversidad) son una decisión del
    equipo documentada en docs/sicop.md, no un indicador oficial.

    `monto_total` suma solo los contratos en colones; los que quedaron en otra
    moneda porque SICOP no trajo tipo de cambio se cuentan aparte en
    `contratos_otra_moneda`, para no sumar montos que no son comparables.

    `base_monto` dice cómo se normalizó el monto: 'monto_por_habitante' si el
    cantón tiene población cargada, 'monto_absoluto' si no. Conviene mirarlo
    antes de leer `sub_monto`, porque cambia lo que ese número significa.

    Un cantón sin contratos queda en 0, no en null: la ausencia de inversión
    municipal ambiental es información, no un dato faltante. Por eso el filtro
    `solo_con_contratos` es opcional y viene apagado.
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

    if solo_con_contratos:
        condiciones.append("contratos > 0")

    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""

    cur.execute(
        """
        SELECT {}
        FROM v_factor_inversion
        {}
        ORDER BY factor_inversion DESC, monto_total DESC
        """.format(COLUMNAS_FACTOR, where),
        parametros,
    )
    return cur.fetchall()


@router.get("/resumen")
def resumen_inversion(cur: Cursor = Depends(get_db)):
    """
    Cuántos contratos ambientales hay por categoría y cuánto suman.
    Sirve para que la interfaz muestre la procedencia de los datos, igual que
    `/ambiental/capas/resumen` con las capas del SNIT.

    No depende de la vista: lee la tabla directamente, así que responde aunque
    todavía no se haya corrido `--calcular-factor`.
    """
    cur.execute(
        """
        SELECT
            c.categoria_detectada AS categoria,
            COUNT(*) AS total,
            SUM(c.monto) FILTER (WHERE c.moneda = 'CRC') AS monto_crc,
            COUNT(*) FILTER (WHERE c.canton_id IS NULL) AS sin_canton,
            MIN(c.fecha_contrato) AS desde,
            MAX(c.fecha_contrato) AS hasta
        FROM contratos_ambientales c
        WHERE c.fuente_id = (SELECT fuente_id FROM fuentes WHERE codigo = 'SICOP')
        GROUP BY c.categoria_detectada
        ORDER BY total DESC
        """
    )
    return cur.fetchall()


@router.get("/factor/{canton_id}")
def obtener_factor_inversion(canton_id: int, cur: Cursor = Depends(get_db)):
    """Factor de Inversión Municipal de un solo cantón, por su id."""
    _exigir_vista(cur)

    cur.execute(
        """
        SELECT {}
        FROM v_factor_inversion
        WHERE canton_id = %s
        """.format(COLUMNAS_FACTOR),
        (canton_id,),
    )
    fila = cur.fetchone()
    if fila is None:
        raise HTTPException(status_code=404, detail="Cantón no encontrado")
    return fila
