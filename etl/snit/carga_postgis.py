"""
Carga de las capas del SNIT en PostGIS — Integrante 1.

Convierte las features GeoJSON en filas de `cantones` y `capas_snit`. Recibe
la conexion ya abierta, para que quien orquesta controle la transaccion.
"""
import json
import unicodedata

from capas import CAPAS


def _sin_tildes(texto):
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def prop(propiedades, *nombres):
    """
    Lee una propiedad tolerando tildes y mayúsculas: la capa de límite cantonal
    del IGN usa claves como 'CANTÓN' y 'CÓDIGO_CANTÓN', que varían entre
    versiones de la capa.
    """
    indice = {_sin_tildes(k).upper(): v for k, v in propiedades.items()}
    for nombre in nombres:
        valor = indice.get(_sin_tildes(nombre).upper())
        if valor is not None:
            return valor
    return None


# ------------------------------------------------------------------


def cargar_cantones(conn, features):
    """
    Carga los 84 cantones en `cantones`. Es idempotente: reejecutar actualiza
    nombre, provincia y geometría sin duplicar filas ni romper las llaves
    foráneas que las otras tres fuentes apuntan a esta tabla.
    """
    cargados = 0
    with conn.cursor() as cur:
        for feature in features:
            props = feature["properties"]
            codigo = prop(props, "CODIGO_CANTON")
            nombre = prop(props, "CANTON")
            provincia = prop(props, "PROVINCIA")
            if codigo is None or nombre is None:
                raise ValueError(
                    "Feature sin código o nombre de cantón: {}".format(list(props))
                )
            cur.execute(
                """
                INSERT INTO cantones (codigo_ine, nombre, provincia, geom)
                VALUES (%s, %s, %s,
                        ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
                ON CONFLICT (codigo_ine) DO UPDATE
                    SET nombre = EXCLUDED.nombre,
                        provincia = EXCLUDED.provincia,
                        geom = EXCLUDED.geom
                """,
                (str(codigo), nombre, provincia, json.dumps(feature["geometry"])),
            )
            cargados += 1
    return cargados


def cargar_capa_snit(conn, tipo_capa, features):
    """
    Reemplaza las filas de un tipo de capa en `capas_snit`.

    Se borra y se vuelve a insertar dentro de la misma transacción en vez de
    hacer upsert, porque el WFS no expone una llave estable por feature: si el
    SINAC republica la capa, los identificadores cambian.
    """
    campo_nombre = CAPAS[tipo_capa].get("campo_nombre")
    cargados = 0

    with conn.cursor() as cur:
        cur.execute("DELETE FROM capas_snit WHERE tipo_capa = %s", (tipo_capa,))
        for feature in features:
            props = feature.get("properties", {})
            nombre = prop(props, campo_nombre) if campo_nombre else None
            cur.execute(
                """
                INSERT INTO capas_snit (fuente_id, tipo_capa, nombre, geom, atributos)
                VALUES (
                    (SELECT fuente_id FROM fuentes WHERE codigo = 'SNIT'),
                    %s, %s,
                    ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                    %s
                )
                """,
                (
                    tipo_capa,
                    nombre,
                    json.dumps(feature["geometry"]),
                    json.dumps(props, ensure_ascii=False),
                ),
            )
            cargados += 1
    return cargados


def asociar_capas_a_cantones(conn):
    """
    Rellena capas_snit.canton_id con el cantón donde cae un punto interior de
    cada geometría. Es solo una etiqueta de conveniencia: una ASP o un río
    pueden cruzar varios cantones, y por eso el Factor Ambiental se calcula con
    intersección espacial real, no con esta columna.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE capas_snit s
               SET canton_id = c.canton_id
              FROM cantones c
             WHERE s.canton_id IS DISTINCT FROM c.canton_id
               AND ST_Intersects(c.geom, ST_PointOnSurface(s.geom))
            """
        )
        return cur.rowcount


# ------------------------------------------------------------------
