"""
ETL — Integrante 1 — SNIT (areas protegidas, corredores biologicos, hidrografia)

Aporta el Factor Ambiental (25%) del Indice de Viabilidad, y ademas carga la
tabla `cantones`, que es la unidad territorial comun contra la que se cruzan
las cuatro fuentes del proyecto.

Este archivo es solo la puerta de entrada: interpreta los argumentos y
coordina los demas modulos de la carpeta.

    capas.py             que capas se usan y en que nodo esta cada una
    descarga_wfs.py      hablar con los servidores del SNIT
    respaldo_local.py    copia en disco de cada capa, con su procedencia
    carga_postgis.py     escribir las features en la base
    factor_ambiental.py  calcular el puntaje por canton

Uso:
    python sync_snit.py --listar-capas                 # los tres nodos
    python sync_snit.py --listar-capas --nodo PNE      # un nodo
    python sync_snit.py --capa cantones --dry-run      # sin base de datos
    python sync_snit.py --todas --calcular-factor
    python sync_snit.py --capa area_protegida --bbox=-85.9,10.1,-85.0,11.0 --dry-run
"""
import argparse
import os
import sys
import time

# La consola de Windows usa cp1252 y rompe los nombres de capa con tilde.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# etl/common/db.py es compartido por las cuatro fuentes del proyecto y no es
# un paquete instalable, asi que se agrega su carpeta al path.
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

from capas import CAPAS, NODOS, url_nodo  # noqa: E402
from carga_postgis import (  # noqa: E402
    asociar_capas_a_cantones,
    cargar_cantones,
    cargar_capa_snit,
)
from db import get_connection, registrar_sincronizacion  # noqa: E402
from descarga_wfs import descargar_capa, listar_capas  # noqa: E402
from factor_ambiental import (  # noqa: E402
    calcular_factor_ambiental,
    refrescar_factor_ambiental,
)
from respaldo_local import guardar_geojson, leer_geojson_respaldo  # noqa: E402


def sincronizar(nombre_capa, dry_run=False, desde_respaldo=False, bbox=None):
    cfg = CAPAS[nombre_capa]
    print(
        "\n>>> {} — {} @ {}".format(nombre_capa, cfg["typename"], url_nodo(nombre_capa))
    )

    if desde_respaldo:
        features = leer_geojson_respaldo(nombre_capa)
        print("  desde respaldo local: {} features".format(len(features)))
    else:
        features = descargar_capa(nombre_capa, bbox=bbox)
        print(
            "  respaldo local: {}".format(
                guardar_geojson(nombre_capa, features, bbox=bbox)
            )
        )

    if dry_run:
        print(
            "  dry-run: {} features descargadas, sin tocar la base".format(len(features))
        )
        return len(features)

    with get_connection() as conn:
        if cfg["destino"] == "cantones":
            total = cargar_cantones(conn, features)
        else:
            total = cargar_capa_snit(conn, nombre_capa, features)
        registrar_sincronizacion(
            conn,
            fuente_codigo="SNIT",
            estado="exito" if total else "parcial",
            registros_procesados=total,
            mensaje="{} -> {} ({})".format(
                cfg["typename"], cfg["destino"], nombre_capa
            ),
        )
    print("  cargadas {} filas en {}".format(total, cfg["destino"]))
    return total


def main():
    parser = argparse.ArgumentParser(description="ETL SNIT (WFS -> PostGIS)")
    parser.add_argument(
        "--listar-capas",
        action="store_true",
        help="GetCapabilities de los nodos y sale",
    )
    parser.add_argument("--nodo", choices=sorted(NODOS), help="Limita --listar-capas")
    parser.add_argument("--capa", choices=sorted(CAPAS), help="Capa a sincronizar")
    parser.add_argument("--todas", action="store_true", help="Sincroniza las 4 capas")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Descarga y guarda el GeoJSON local, sin escribir en la base",
    )
    parser.add_argument(
        "--desde-respaldo",
        action="store_true",
        help="Carga desde el GeoJSON local en data/ sin llamar al WFS "
        "(respaldo si el nodo del SNIT está caído)",
    )
    parser.add_argument(
        "--bbox",
        help="Filtro espacial 'minlon,minlat,maxlon,maxlat' en grados. Como el "
        "valor empieza con '-', hay que escribirlo pegado con '=': "
        "--bbox=-85.9,10.1,-85.0,11.0. Sin esto se trae la capa nacional completa",
    )
    parser.add_argument(
        "--calcular-factor",
        action="store_true",
        help="Crea la vista v_factor_ambiental y muestra el ranking de cantones",
    )
    args = parser.parse_args()

    if args.listar_capas:
        listar_capas(args.nodo)
        return

    if args.calcular_factor and not (args.capa or args.todas):
        calcular_factor_ambiental()
        return

    if args.todas:
        # cantones primero: las demás capas se asocian contra esa tabla.
        objetivo = ["cantones", "area_protegida", "corredor_biologico", "hidrografia"]
    elif args.capa:
        objetivo = [args.capa]
    else:
        parser.error("indique --capa, --todas o --listar-capas")

    try:
        for nombre_capa in objetivo:
            sincronizar(
                nombre_capa,
                dry_run=args.dry_run,
                desde_respaldo=args.desde_respaldo,
                bbox=args.bbox,
            )
        if not args.dry_run:
            with get_connection() as conn:
                print(
                    "\nOK: {} geometrías asociadas a un cantón".format(
                        asociar_capas_a_cantones(conn)
                    )
                )
            if args.calcular_factor:
                calcular_factor_ambiental()
            else:
                # Las capas cambiaron: el factor guardado quedaría desactualizado.
                # El refresco recalcula el cruce espacial y tarda unos 5 minutos,
                # así que se avisa antes para que no parezca que se colgó.
                print(
                    "\nRefrescando el Factor Ambiental con las capas nuevas "
                    "(unos 5 minutos)..."
                )
                inicio_refresco = time.time()
                if refrescar_factor_ambiental():
                    print(
                        "Factor Ambiental refrescado en {:.0f} s".format(
                            time.time() - inicio_refresco
                        )
                    )
                else:
                    print(
                        "La vista v_factor_ambiental aún no existe. "
                        "Créela con --calcular-factor"
                    )
    except Exception as exc:
        if not args.dry_run:
            with get_connection() as conn:
                registrar_sincronizacion(
                    conn, fuente_codigo="SNIT", estado="error", mensaje=str(exc)
                )
        raise


if __name__ == "__main__":
    main()
