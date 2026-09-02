"""
ETL — Integrante 1 — SNIT (áreas protegidas, corredores biológicos, hidrografía)

Flujo:
  1. GetCapabilities contra el nodo WFS de SNIT, para confirmar el nombre
     exacto de las capas disponibles (varía según nodo).
  2. GetFeature por capa, salida GeoJSON, reproyectado a EPSG:4326.
  3. Normalizar cada feature y cargarlo en `capas_snit`.

Ejecutar de forma aislada primero (sin base de datos) con:
    python sync_snit.py --listar-capas
para confirmar qué capas expone el nodo antes de programar el resto.

Uso:
    python sync_snit.py --listar-capas
    python sync_snit.py --capa <nombre_capa> --tipo area_protegida
"""
import argparse
import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

from dotenv import load_dotenv
from owslib.wfs import WebFeatureService

from db import get_connection, registrar_sincronizacion  # noqa: E402

load_dotenv()

SNIT_WFS_BASE_URL = os.environ.get(
    "SNIT_WFS_BASE_URL", "https://www.snitcr.go.cr/be/geoserver/wfs"
)
SNIT_WFS_VERSION = os.environ.get("SNIT_WFS_VERSION", "2.0.0")

# Tipos de capa que el índice de viabilidad necesita (Factor Ambiental).
# El nombre real de la capa en el nodo se confirma con --listar-capas
# y se documenta en docs/snit.md una vez validado.
TIPOS_CAPA_OBJETIVO = ["area_protegida", "corredor_biologico", "hidrografia"]


def conectar_wfs() -> WebFeatureService:
    return WebFeatureService(url=SNIT_WFS_BASE_URL, version=SNIT_WFS_VERSION)


def listar_capas() -> None:
    wfs = conectar_wfs()
    print(f"Capas disponibles en {SNIT_WFS_BASE_URL} (v{SNIT_WFS_VERSION}):")
    for nombre in sorted(wfs.contents):
        print(f"  - {nombre}")


def descargar_capa(nombre_capa: str) -> dict:
    wfs = conectar_wfs()
    response = wfs.getfeature(typename=nombre_capa, outputFormat="application/json")
    return json.loads(response.read())


def cargar_capa(tipo_capa: str, nombre_capa: str) -> int:
    geojson = descargar_capa(nombre_capa)
    features = geojson.get("features", [])

    with get_connection() as conn:
        with conn.cursor() as cur:
            for feature in features:
                geom = json.dumps(feature["geometry"])
                props = json.dumps(feature.get("properties", {}))
                nombre = feature.get("properties", {}).get("nombre") or feature.get(
                    "properties", {}
                ).get("name")
                cur.execute(
                    """
                    INSERT INTO capas_snit
                        (fuente_id, tipo_capa, nombre, geom, atributos)
                    VALUES (
                        (SELECT fuente_id FROM fuentes WHERE codigo = 'SNIT'),
                        %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s
                    )
                    """,
                    (tipo_capa, nombre, geom, props),
                )
        registrar_sincronizacion(
            conn,
            fuente_codigo="SNIT",
            estado="exito" if features else "parcial",
            registros_procesados=len(features),
            mensaje=f"Capa '{nombre_capa}' → tipo_capa '{tipo_capa}'",
        )
    return len(features)


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL SNIT (WFS → PostGIS)")
    parser.add_argument(
        "--listar-capas", action="store_true", help="Imprime GetCapabilities y sale"
    )
    parser.add_argument("--capa", help="Nombre exacto de la capa WFS a descargar")
    parser.add_argument(
        "--tipo",
        choices=TIPOS_CAPA_OBJETIVO,
        help="Tipo de capa objetivo para el índice de viabilidad",
    )
    args = parser.parse_args()

    if args.listar_capas:
        listar_capas()
        return

    if not args.capa or not args.tipo:
        parser.error("--capa y --tipo son requeridos (o usa --listar-capas)")

    try:
        total = cargar_capa(args.tipo, args.capa)
        print(f"OK: {total} features cargadas de '{args.capa}' como '{args.tipo}'")
    except Exception as exc:
        with get_connection() as conn:
            registrar_sincronizacion(
                conn, fuente_codigo="SNIT", estado="error", mensaje=str(exc)
            )
        raise


if __name__ == "__main__":
    main()
