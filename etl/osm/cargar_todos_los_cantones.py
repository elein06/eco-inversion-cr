"""
Carga masiva — Integrante 3 — OSM/Overpass para TODOS los cantones.

En vez de adivinar un bbox a mano por cantón, calcula el bbox real de cada
uno a partir de su geometría ya cargada en la tabla `cantones` (por
load_cantones.py) con ST_Extent, y llama a `sincronizar_canton` de
sync_osm.py para cada uno, con una pausa entre consultas para respetar el
uso justo de la instancia pública de Overpass (piden ~1 consulta/segundo,
sin paralelismo).

Uso:
    python cargar_todos_los_cantones.py                # todos los cantones
    python cargar_todos_los_cantones.py --limite 10     # solo los primeros 10 (prueba rápida)
    python cargar_todos_los_cantones.py --pausa 2       # 2 segundos entre consultas (default 1.5)
    python cargar_todos_los_cantones.py --forzar        # ignora la caché de 7 días
"""
import argparse
import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

from db import get_connection  # noqa: E402
from sync_osm import sincronizar_canton  # noqa: E402


def obtener_cantones_con_bbox(limite: int | None) -> list[tuple[str, str]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    nombre,
                    ST_YMin(geom) AS minlat, ST_XMin(geom) AS minlon,
                    ST_YMax(geom) AS maxlat, ST_XMax(geom) AS maxlon
                FROM cantones
                ORDER BY nombre
                """
            )
            filas = cur.fetchall()

    if limite:
        filas = filas[:limite]

    return [
        (nombre, f"{minlat},{minlon},{maxlat},{maxlon}")
        for nombre, minlat, minlon, maxlat, maxlon in filas
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga OSM/Overpass para todos los cantones de la tabla `cantones`")
    parser.add_argument("--limite", type=int, help="Solo cargar los primeros N cantones (prueba rápida)")
    parser.add_argument("--pausa", type=float, default=3.0, help="Segundos de espera entre consultas a Overpass")
    parser.add_argument("--forzar", action="store_true", help="Ignora la caché de 7 días")
    args = parser.parse_args()

    cantones = obtener_cantones_con_bbox(args.limite)
    if not cantones:
        print("No hay cantones en la tabla `cantones`. Corré load_cantones.py primero.")
        return

    print(f"Cargando OSM/Overpass para {len(cantones)} cantones (pausa {args.pausa}s entre consultas)...\n")

    exitosos, fallidos, sin_cambios = 0, 0, 0
    for i, (nombre, bbox) in enumerate(cantones, start=1):
        print(f"[{i}/{len(cantones)}] {nombre} (bbox {bbox})", end=" ... ")
        try:
            total = sincronizar_canton(nombre, bbox, forzar=args.forzar)
            if total > 0:
                print(f"OK: {total} POIs")
                exitosos += 1
            else:
                print("sin datos nuevos (caché vigente o sin POIs en la zona)")
                sin_cambios += 1
        except Exception as exc:
            print(f"ERROR: {exc}")
            fallidos += 1

        if i < len(cantones):
            time.sleep(args.pausa)

    print(f"\nResumen: {exitosos} con datos nuevos, {sin_cambios} sin cambios, {fallidos} con error.")
    print("Recordá recalcular el índice después:")
    print("  curl.exe -X POST http://localhost:8000/indice-viabilidad/recalcular")


if __name__ == "__main__":
    main()
