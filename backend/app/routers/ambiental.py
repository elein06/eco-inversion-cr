"""
Router de la fuente SNIT 

Expone las capas territoriales (áreas silvestres protegidas, corredores
biológicos e hidrografía) y el Factor Ambiental por cantón.

Es el equivalente de lo que `infraestructura.py` hace con OSM: el frontend
nunca habla con el SNIT, solo con estos endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extensions import cursor as Cursor

from app.database import get_db

router = APIRouter(prefix="/ambiental", tags=["ambiental (SNIT)"])

TIPOS_CAPA = ("area_protegida", "corredor_biologico", "hidrografia")


def resolver_canton(cur: Cursor, canton_id: int | None, canton: str | None) -> int | None:
    """
    Traduce un nombre de cantón a su canton_id.

    El frontend manda el id, que lo obtiene del clic en el mapa. Pero una
    persona consultando la API a mano piensa en nombres, no en números, así que
    ambos parámetros son válidos y el nombre tiene prioridad si vienen los dos.

    La comparación ignora mayúsculas y tildes con `unaccent`, para que 'dota',
    'Dota' y 'DOTA' encuentren lo mismo, y 'Poas' encuentre 'Poás'.
    """
    if not canton:
        return canton_id

    cur.execute(
        """
        SELECT canton_id
        FROM cantones
        WHERE unaccent(lower(nombre)) = unaccent(lower(%s))
        """,
        (canton,),
    )
    fila = cur.fetchone()
    if fila:
        return fila["canton_id"]

    # Sin coincidencia exacta: se sugieren parecidos en vez de devolver vacío,
    # que dejaría al usuario sin saber si escribió mal o si no hay datos.
    cur.execute(
        """
        SELECT nombre
        FROM cantones
        WHERE unaccent(lower(nombre)) LIKE unaccent(lower(%s))
        ORDER BY nombre
        LIMIT 5
        """,
        ("%{}%".format(canton),),
    )
    sugerencias = [f["nombre"] for f in cur.fetchall()]
    detalle = "No existe el cantón '{}'.".format(canton)
    if sugerencias:
        detalle += " ¿Quiso decir: {}?".format(", ".join(sugerencias))
    raise HTTPException(status_code=404, detail=detalle)


@router.get("/capas")
def listar_capas(
    cur: Cursor = Depends(get_db),
    tipo: str | None = Query(
        None,
        description="Filtra por tipo: area_protegida, corredor_biologico o hidrografia",
    ),
    canton: str | None = Query(None, description="Nombre del cantón, ej. Dota"),
    canton_id: int | None = Query(None, description="Id del cantón, alternativa a canton"),
    limite: int = Query(500, ge=1, le=5000),
):
    """
    Capas del SNIT en GeoJSON, listas para dibujar en el mapa.

    Se pagina con `limite` porque la hidrografía tiene 6 331 líneas y devolverlas
    todas de golpe pesa varios megabytes.

    El filtro por cantón usa intersección espacial real (ST_Intersects) y no la
    columna canton_id, porque un río o un área protegida pueden cruzar varios
    cantones y esa columna guarda solo uno.
    """
    if tipo and tipo not in TIPOS_CAPA:
        raise HTTPException(
            status_code=400,
            detail="tipo inválido. Use uno de: {}".format(", ".join(TIPOS_CAPA)),
        )

    canton_id = resolver_canton(cur, canton_id, canton)

    condiciones = []
    parametros: list = []

    if tipo:
        condiciones.append("s.tipo_capa = %s")
        parametros.append(tipo)

    if canton_id:
        condiciones.append(
            "EXISTS (SELECT 1 FROM cantones c "
            "WHERE c.canton_id = %s AND ST_Intersects(c.geom, s.geom))"
        )
        parametros.append(canton_id)

    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""
    parametros.append(limite)

    cur.execute(
        """
        SELECT
            s.capa_id,
            s.tipo_capa,
            s.nombre,
            s.atributos,
            s.fecha_consulta,
            ST_AsGeoJSON(s.geom)::json AS geom
        FROM capas_snit s
        {}
        ORDER BY s.tipo_capa, s.nombre NULLS LAST
        LIMIT %s
        """.format(where),
        parametros,
    )
    return cur.fetchall()


@router.get("/capas/resumen")
def resumen_capas(cur: Cursor = Depends(get_db)):
    """
    Cuántas geometrías hay por tipo de capa y cuándo se sincronizaron.
    Sirve para que la interfaz muestre la procedencia de los datos.
    """
    cur.execute(
        """
        SELECT
            s.tipo_capa,
            COUNT(*) AS total,
            MAX(s.fecha_consulta) AS ultima_consulta
        FROM capas_snit s
        GROUP BY s.tipo_capa
        ORDER BY s.tipo_capa
        """
    )
    return cur.fetchall()


@router.get("/factor")
def listar_factor_ambiental(
    cur: Cursor = Depends(get_db),
    canton: str | None = Query(None, description="Nombre del cantón, ej. Dota"),
    provincia: str | None = Query(None, description="Nombre de la provincia"),
):
    """
    Factor Ambiental por cantón, con el desglose de sus tres sub-puntajes.

    Sale de la vista materializada v_factor_ambiental, que calcula el ETL del
    SNIT. Los pesos internos (50% ASP, 30% corredor, 20% hidrografía) y los
    umbrales son una decisión del equipo documentada en docs/snit.md, no un
    indicador oficial.
    """
    condiciones = []
    parametros: list = []

    if canton:
        condiciones.append("unaccent(lower(nombre)) = unaccent(lower(%s))")
        parametros.append(canton)

    if provincia:
        condiciones.append("unaccent(lower(provincia)) = unaccent(lower(%s))")
        parametros.append(provincia)

    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""

    cur.execute(
        """
        SELECT
            canton_id, codigo_ine, nombre, provincia, area_km2,
            pct_area_protegida, pct_corredor_biologico,
            densidad_drenaje_km_km2,
            sub_asp, sub_corredor, sub_hidro,
            factor_ambiental
        FROM v_factor_ambiental
        {}
        ORDER BY factor_ambiental DESC
        """.format(where),
        parametros,
    )
    return cur.fetchall()


@router.get("/factor/{canton_id}")
def obtener_factor_ambiental(canton_id: int, cur: Cursor = Depends(get_db)):
    """Factor Ambiental de un solo cantón, por su id."""
    cur.execute(
        """
        SELECT
            canton_id, codigo_ine, nombre, provincia, area_km2,
            pct_area_protegida, pct_corredor_biologico,
            densidad_drenaje_km_km2,
            sub_asp, sub_corredor, sub_hidro,
            factor_ambiental
        FROM v_factor_ambiental
        WHERE canton_id = %s
        """,
        (canton_id,),
    )
    fila = cur.fetchone()
    if fila is None:
        raise HTTPException(status_code=404, detail="Cantón no encontrado")
    return fila