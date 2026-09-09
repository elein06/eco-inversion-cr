"""
ETL — Integrante 3 — OpenStreetMap / Overpass API (conectividad e infraestructura)

Flujo:
  1. Consultar Overpass QL por cantón para POIs relevantes (centros de
     acopio, escuelas, vías principales).
  2. Convertir el resultado a GeoJSON con osm2geojson.
  3. Cargar/actualizar en `infraestructura_osm` con `valido_hasta = now() + 7 días`.

La caché es obligatoria: antes de consultar Overpass, el backend (o este
script) debe revisar si ya hay filas vigentes (`valido_hasta > now()`) para
el cantón, dado el límite de uso de las instancias públicas de Overpass.

Uso:
    python sync_osm.py --canton "San José" --bbox 9.9,-84.1,9.95,-84.05
"""
import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

import time

import osm2geojson
import overpy
import requests
from dotenv import load_dotenv

from db import get_canton_id_por_nombre, get_connection, registrar_sincronizacion  # noqa: E402
from factor_conectividad import calcular_factor_conectividad  # noqa: E402

load_dotenv()

OVERPASS_API_URL = os.environ.get("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter")
OSM_CACHE_DIAS = int(os.environ.get("OSM_CACHE_DIAS", "7"))

CATEGORIAS_OSM = {
    "amenity=recycling": "centro_acopio",
    "amenity=school": "escuela",
    "highway=primary": "via_principal",
    "highway=secondary": "via_principal",
}


def construir_query(bbox: str) -> str:
    return f"""
    [out:json][timeout:25];
    (
      node["amenity"="recycling"]({bbox});
      node["amenity"="school"]({bbox});
      way["highway"~"primary|secondary"]({bbox});
    );
    out center tags;
    """


# Instancia principal + un espejo de respaldo, por si la pública oficial
# está saturada (429 Too Many Requests / 504 Gateway Timeout son comunes
# cuando se consulta un cantón detrás de otro en una corrida masiva).
_INSTANCIAS_OVERPASS = [
    OVERPASS_API_URL,
    "https://overpass.kumi.systems/api/interpreter",
]

_HEADERS_OVERPASS = {
    "User-Agent": (
        "eco-inversion-cr-osm-etl/1.0 "
        "(proyecto universitario; contacto: kaaarmkpop@gmail.com)"
    )
}


def consultar_overpass(query: str, intentos_por_instancia: int = 3) -> dict:
    """
    Hace la petición a Overpass con `requests` y un User-Agent descriptivo,
    en vez de usar overpy.Overpass.query() directamente: ese método llama a
    `urllib.request.urlopen` con el User-Agent por defecto de Python
    ("Python-urllib/x.y"), y overpass-api.de lo rechaza con 406 Not
    Acceptable (piden un User-Agent que identifique la aplicación).

    Reintenta con espera progresiva (5s, 10s, 20s...) ante 429 (demasiadas
    consultas) y 504 (servidor saturado) — esperable en corridas masivas
    contra la instancia pública. Si una instancia agota sus reintentos,
    prueba con la siguiente de `_INSTANCIAS_OVERPASS` antes de rendirse.

    Devuelve el JSON crudo de Overpass. overpy.Result.from_json(...) lo
    convierte a objetos Node/Way cuando hace falta, y osm2geojson.json2geojson(...)
    lo convierte a GeoJSON — ambos a partir del mismo JSON, sin repetir la consulta.
    """
    instancias = list(dict.fromkeys(_INSTANCIAS_OVERPASS))  # sin duplicar si ya coincide
    ultimo_error: Exception | None = None

    for url in instancias:
        espera = 5.0
        for intento in range(1, intentos_por_instancia + 1):
            try:
                resp = requests.post(url, data={"data": query}, headers=_HEADERS_OVERPASS, timeout=60)
            except requests.RequestException as exc:
                ultimo_error = exc
            else:
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in (429, 504):
                    ultimo_error = requests.exceptions.HTTPError(
                        f"{resp.status_code} de Overpass ({url})"
                    )
                else:
                    resp.raise_for_status()

            if intento < intentos_por_instancia:
                print(f"    ({url.split('/')[2]}, intento {intento}/{intentos_por_instancia} falló: "
                      f"{ultimo_error} — reintentando en {espera:.0f}s)")
                time.sleep(espera)
                espera *= 2
        print(f"    {url.split('/')[2]} agotó sus reintentos, probando siguiente instancia...")

    raise ultimo_error  # todas las instancias fallaron


def hay_cache_vigente(conn, canton_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM infraestructura_osm
            WHERE canton_id = %s AND valido_hasta > now()
            LIMIT 1
            """,
            (canton_id,),
        )
        return cur.fetchone() is not None


def categorizar(tags: dict) -> str | None:
    for clave_valor, categoria in CATEGORIAS_OSM.items():
        clave, valor = clave_valor.split("=")
        if tags.get(clave) == valor:
            return categoria
    return None


_SQL_INSERTAR_POI = """
    INSERT INTO infraestructura_osm
        (fuente_id, canton_id, osm_id, osm_tipo, categoria, nombre, geom)
    SELECT
        (SELECT fuente_id FROM fuentes WHERE codigo = 'OSM'),
        %(canton_id)s, %(osm_id)s, %(osm_tipo)s, %(categoria)s, %(nombre)s,
        ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)
    WHERE ST_Contains(
        (SELECT geom FROM cantones WHERE canton_id = %(canton_id)s),
        ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)
    )
    ON CONFLICT (osm_id, osm_tipo) DO UPDATE
        SET canton_id = EXCLUDED.canton_id,
            fecha_consulta = now(),
            valido_hasta = now() + interval '{dias} days'
""".format(dias=OSM_CACHE_DIAS)


def sincronizar_canton(nombre_canton: str, bbox: str, forzar: bool = False) -> int:
    with get_connection() as conn:
        canton_id = get_canton_id_por_nombre(conn, nombre_canton)
        if canton_id is None:
            raise ValueError(f"Cantón '{nombre_canton}' no existe en la tabla cantones")

        if not forzar and hay_cache_vigente(conn, canton_id):
            print(f"Caché vigente para '{nombre_canton}' (<{OSM_CACHE_DIAS} días) — no se consulta Overpass")
            return 0

        datos_crudos = consultar_overpass(construir_query(bbox))
        resultado = overpy.Result.from_json(datos_crudos)

        # El bbox que se consulta es un rectángulo (el ST_Extent del cantón),
        # y los cantones de Costa Rica casi nunca son rectangulares — así que
        # el bbox siempre agarra pedazo de los cantones vecinos (a veces hasta
        # fuera del país, en zonas costeras o fronterizas). Por eso cada punto
        # se valida contra el polígono REAL del cantón (ST_Contains) antes de
        # insertarlo: lo que cae fuera se descarta acá, no se le asigna a
        # `nombre_canton` solo porque apareció en su bbox. El ON CONFLICT
        # también actualiza canton_id — así, si un punto ya había quedado mal
        # asignado por una corrida vieja (antes de este filtro), la próxima
        # vez que el cantón dueño real lo consulte, se corrige solo.
        insertados = 0
        descartados = 0
        with conn.cursor() as cur:
            for nodo in resultado.nodes:
                categoria = categorizar(nodo.tags)
                if not categoria:
                    continue
                cur.execute(
                    _SQL_INSERTAR_POI,
                    {
                        "canton_id": canton_id,
                        "osm_id": nodo.id,
                        "osm_tipo": "node",
                        "categoria": categoria,
                        "nombre": nodo.tags.get("name"),
                        "lon": float(nodo.lon),
                        "lat": float(nodo.lat),
                    },
                )
                if cur.rowcount:
                    insertados += 1
                else:
                    descartados += 1

            for way in resultado.ways:
                categoria = categorizar(way.tags)
                if not categoria or not way.center_lon:
                    continue
                cur.execute(
                    _SQL_INSERTAR_POI,
                    {
                        "canton_id": canton_id,
                        "osm_id": way.id,
                        "osm_tipo": "way",
                        "categoria": categoria,
                        "nombre": way.tags.get("name"),
                        "lon": float(way.center_lon),
                        "lat": float(way.center_lat),
                    },
                )
                if cur.rowcount:
                    insertados += 1
                else:
                    descartados += 1

        if descartados:
            print(
                f"  {descartados} elemento(s) descartado(s): el bbox de '{nombre_canton}' los trajo, "
                "pero caen fuera de su polígono real (zona de un cantón vecino, o fuera de Costa Rica)"
            )

        registrar_sincronizacion(
            conn,
            fuente_codigo="OSM",
            estado="exito" if insertados else "parcial",
            registros_procesados=insertados,
            mensaje=f"Cantón: {nombre_canton}, bbox: {bbox}, descartados por polígono: {descartados}",
        )
        return insertados


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL OSM/Overpass (POIs → PostGIS, con caché)")
    parser.add_argument("--canton", help="Nombre del cantón (debe existir en tabla cantones)")
    parser.add_argument("--bbox", help="minlat,minlon,maxlat,maxlon")
    parser.add_argument("--forzar", action="store_true", help="Ignora la caché de 7 días")
    parser.add_argument(
        "--calcular-factor",
        action="store_true",
        help="Crea/recrea la vista v_factor_conectividad y muestra el ranking",
    )
    args = parser.parse_args()

    # --calcular-factor solo (sin --canton): recrea la vista con lo que ya
    # esté cargado, sin consultar Overpass. Útil después de una carga masiva
    # con cargar_todos_los_cantones.py, o para refrescar el ranking a mano.
    if args.calcular_factor and not args.canton:
        calcular_factor_conectividad()
        return

    if not args.canton or not args.bbox:
        parser.error("indique --canton y --bbox, o --calcular-factor solo")

    try:
        total = sincronizar_canton(args.canton, args.bbox, forzar=args.forzar)
        print(f"OK: {total} POIs cargados/actualizados para '{args.canton}'")
        if args.calcular_factor:
            calcular_factor_conectividad()
    except Exception as exc:
        with get_connection() as conn:
            registrar_sincronizacion(conn, fuente_codigo="OSM", estado="error", mensaje=str(exc))
        raise


if __name__ == "__main__":
    main()
