"""
Prueba aislada — Integrante 3 — Overpass API (SIN base de datos)

Objetivo (semana 1, día 1-2 del plan): confirmar que podemos consumir la
fuente por nuestra cuenta, sin depender de que Postgres/PostGIS ni las
otras fuentes estén listas. Este script NO escribe en la base de datos:
solo consulta Overpass, categoriza el resultado y lo imprime en consola
(y opcionalmente lo guarda como GeoJSON local para inspeccionarlo en
QGIS/geojson.io).

Reutiliza las mismas funciones (`construir_query`, `categorizar`) que
usará `sync_osm.py` para que, cuando conectemos a la base, el
comportamiento sea idéntico al que ya validamos aquí.

Uso:
    python test_overpass.py --bbox 9.9,-84.15,9.98,-84.05
    python test_overpass.py --bbox 9.9,-84.15,9.98,-84.05 --guardar salida.geojson

bbox = minlat,minlon,maxlat,maxlon (igual formato que sync_osm.py)
Podés sacar un bbox rápido de un cantón en https://boundingbox.klokantech.com/
"""
import argparse
import json
import sys

import osm2geojson
import overpy

from sync_osm import CATEGORIAS_OSM, OVERPASS_API_URL, categorizar, construir_query, consultar_overpass


def probar(bbox: str, guardar: str | None) -> None:
    print(f"Consultando Overpass ({OVERPASS_API_URL}) para bbox={bbox} ...")

    try:
        datos_crudos = consultar_overpass(construir_query(bbox))
        resultado = overpy.Result.from_json(datos_crudos)
    except Exception as exc:
        print(f"ERROR al consultar Overpass: {exc}", file=sys.stderr)
        print(
            "Posibles causas: bbox mal formado, timeout de la instancia pública, "
            "o límite de uso alcanzado. Reintentá en unos minutos.",
            file=sys.stderr,
        )
        sys.exit(1)

    conteo = {categoria: 0 for categoria in set(CATEGORIAS_OSM.values())}
    conteo["sin_categoria"] = 0
    muestras = []

    for nodo in resultado.nodes:
        categoria = categorizar(nodo.tags) or "sin_categoria"
        conteo[categoria] = conteo.get(categoria, 0) + 1
        if len(muestras) < 10:
            muestras.append(
                {
                    "tipo": "node",
                    "id": nodo.id,
                    "categoria": categoria,
                    "nombre": nodo.tags.get("name", "(sin nombre)"),
                    "lat": float(nodo.lat),
                    "lon": float(nodo.lon),
                }
            )

    for way in resultado.ways:
        categoria = categorizar(way.tags) or "sin_categoria"
        conteo[categoria] = conteo.get(categoria, 0) + 1
        if len(muestras) < 10 and way.center_lat:
            muestras.append(
                {
                    "tipo": "way",
                    "id": way.id,
                    "categoria": categoria,
                    "nombre": way.tags.get("name", "(sin nombre)"),
                    "lat": float(way.center_lat),
                    "lon": float(way.center_lon),
                }
            )

    print("\n--- Resultado ---")
    print(f"Nodes: {len(resultado.nodes)} | Ways: {len(resultado.ways)}")
    print("Conteo por categoría:")
    for categoria, n in sorted(conteo.items(), key=lambda kv: -kv[1]):
        print(f"  {categoria}: {n}")

    print("\nMuestra (hasta 10 elementos):")
    for m in muestras:
        print(f"  [{m['tipo']}:{m['id']}] {m['categoria']} — {m['nombre']} ({m['lat']:.5f}, {m['lon']:.5f})")

    if guardar:
        # Reutiliza el mismo JSON crudo ya obtenido — no vuelve a consultar Overpass.
        geojson = osm2geojson.json2geojson(datos_crudos)
        with open(guardar, "w", encoding="utf-8") as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)
        print(f"\nGeoJSON guardado en: {guardar} (abrilo en https://geojson.io para verlo en el mapa)")

    print("\nOK: la consulta a Overpass funciona de forma aislada, sin tocar la base de datos.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prueba aislada de Overpass API (sin DB)")
    parser.add_argument("--bbox", required=True, help="minlat,minlon,maxlat,maxlon")
    parser.add_argument("--guardar", help="Ruta de archivo .geojson para guardar el resultado (opcional)")
    args = parser.parse_args()
    probar(args.bbox, args.guardar)


if __name__ == "__main__":
    main()
