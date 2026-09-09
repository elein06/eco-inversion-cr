"""
ETL — Integrante 2 — SICOP (inversión municipal ambiental)

Flujo:
  1. Leer un reporte descargado manualmente del módulo de datos abiertos de
     SICOP (Excel/CSV/JSON) — SICOP no ofrece una API REST limpia.
  2. Clasificar cada contrato como "ambiental" con un filtro de palabras
     clave por regex sobre la descripción del objeto contractual, agrupadas
     en 6 categorías (ver PALABRAS_CLAVE_AMBIENTAL) — no machine learning.
  3. Cargar los contratos ambientales en `contratos_ambientales`.
  4. Con --calcular-factor: crear/recrear v_factor_inversion, que convierte
     esos contratos en el Factor de Inversión Municipal del índice.

Uso:
    python sync_sicop.py --archivo reportes/contratos_2025.xlsx
    python sync_sicop.py --archivo reportes/contratos_2025.xlsx --calcular-factor
    python sync_sicop.py --calcular-factor                         # solo recrea la vista
"""
import argparse
import glob
import os
import sys
from datetime import date, timedelta

# La consola de Windows usa cp1252 y rompe los nombres con tilde.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# etl/common/db.py es compartido por las cuatro fuentes del proyecto y no es un
# paquete instalable, así que se agrega su carpeta al path.
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

import pandas as pd
from dotenv import load_dotenv

from db import get_canton_id_por_nombre, get_connection, registrar_sincronizacion  # noqa: E402
from factor_inversion import calcular_factor_inversion  # noqa: E402

load_dotenv()

# Criterio explícito y documentado (ver docs/sicop.md) — no es machine learning.
# Las palabras clave se agrupan en 6 categorías (no se guarda la palabra que
# matcheó tal cual): son las mismas 6 que conoce el frontend
# (frontend/src/SICOP/estilos.ts) y el denominador de sub_diversidad en
# etl/sicop/factor_inversion.py. Varias palabras pueden apuntar a la misma
# categoría (con y sin tilde, o sinónimos cercanos).
PALABRAS_CLAVE_AMBIENTAL: dict[str, list[str]] = {
    "residuos": ["residuos"],
    "reciclaje": ["reciclaje"],
    "agua": ["alcantarillado", "tratamiento de aguas"],
    "areas_verdes": ["arborizacion", "arborización", "reforestacion", "reforestación"],
    "infraestructura_verde": ["infraestructura verde"],
    "gestion_ambiental": ["gestion ambiental", "gestión ambiental"],
}
PATRONES_POR_CATEGORIA: dict[str, re.Pattern] = {
    categoria: re.compile("|".join(re.escape(p) for p in palabras), re.IGNORECASE)
    for categoria, palabras in PALABRAS_CLAVE_AMBIENTAL.items()
}


def confirmar_y_bajar(nombre, report_id, codigo, formato, espera_max):
    """
    Confirma el código recibido por correo y, ya con el reporte
    construyéndose, espera y lo baja. Es el paso que cierra el ciclo.

def clasificar(descripcion: str) -> str | None:
    """Devuelve la categoría (una de las 6 de PALABRAS_CLAVE_AMBIENTAL) o None
    si ninguna palabra clave aparece en la descripción del objeto contractual."""
    if not isinstance(descripcion, str):
        return None
    for categoria, patron in PATRONES_POR_CATEGORIA.items():
        if patron.search(descripcion):
            return categoria
    return None


def archivos_locales(rutas_o_patrones):
    """Expande rutas y comodines; si no se pasó nada, usa todo `data/`."""
    if not rutas_o_patrones:
        patrones = [os.path.join(DIR_DATOS, "*")]
    else:
        patrones = rutas_o_patrones

    rutas = []
    for patron in patrones:
        encontrados = sorted(glob.glob(patron))
        if not encontrados and os.path.exists(patron):
            encontrados = [patron]
        for ruta in encontrados:
            if os.path.isfile(ruta) and not ruta.endswith(
                (".meta.json", ".confirm.json", ".gitkeep")
            ):
                rutas.append(ruta)
    return rutas


def cargar(rutas, solo_municipalidades, dry_run, desde, hasta):
    print("\nLeyendo reportes descargados:")
    tablas = cargar_tablas(rutas)
    if not tablas:
        raise ValueError(
            "No se pudo leer ningún reporte. Baje los reportes primero con "
            "'python sync_sicop.py --solicitar --todos'."
        )

    df, stats = construir_dataset(tablas, solo_municipalidades=solo_municipalidades)

    print("\nResultado de la clasificación:")
    for clave in (
        "contratos",
        "carteles",
        "instituciones",
        "contratos_sin_lineas",
        "contratos_sin_cartel",
        "contratos_sin_institucion",
        "descartados_no_municipales",
        "evaluados",
        "ambientales",
        "no_ambientales",
    ):
        if clave in stats:
            print("  {:<28} {}".format(clave, stats[clave]))

    if len(df):
        print("\nContratos ambientales por categoría detectada:")
        for categoria, cantidad in df["categoria_detectada"].value_counts().items():
            monto = df.loc[df["categoria_detectada"] == categoria, "monto"].sum()
            print("  {:<22} {:>5} contratos  {:>18,.2f}".format(
                categoria, cantidad, monto))

    if dry_run:
        print(
            "\ndry-run: {} contratos ambientales detectados, sin tocar la "
            "base".format(len(df))
        )
        if len(df):
            print("\nMuestra (primeras 5 filas):")
            for _, fila in df.head(5).iterrows():
                print(
                    "  [{}] {} | {} | {:,.2f} {} | {}".format(
                        fila["categoria_detectada"],
                        str(fila["institucion"])[:34],
                        str(fila["canton"])[:16],
                        float(fila["monto"]),
                        fila["moneda"],
                        str(fila["descripcion_objeto"])[:60],
                    )
                )
        return len(df)

    with get_connection() as conn:
        insertados, sin_canton, borrados = cargar_contratos(
            conn, df, desde=desde, hasta=hasta
        )
        registrar_sincronizacion(
            conn,
            fuente_codigo="SICOP",
            estado="exito" if insertados else "parcial",
            registros_procesados=insertados,
            mensaje=(
                "periodo {} a {}; evaluados {}, ambientales {}, "
                "sin cantón {}, reemplazados {}; archivos: {}".format(
                    desde,
                    hasta,
                    stats.get("evaluados", 0),
                    stats.get("ambientales", 0),
                    sin_canton,
                    borrados,
                    ", ".join(os.path.basename(r) for r in rutas),
                )
            ),
        )

    print(
        "\nOK: {} contratos ambientales cargados ({} sin cantón resuelto, "
        "{} filas del periodo reemplazadas)".format(insertados, sin_canton, borrados)
    )
    return insertados


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL SICOP (reporte → clasificación → PostgreSQL)")
    parser.add_argument("--archivo", help="Ruta al reporte descargado (xlsx/csv)")
    parser.add_argument(
        "--calcular-factor",
        action="store_true",
        help="Crea/recrea la vista v_factor_inversion y muestra el ranking",
    )
    args = parser.parse_args()

    # --calcular-factor solo (sin --archivo): recrea la vista con lo que ya
    # esté cargado, sin procesar ningún reporte nuevo. Mismo criterio que
    # sync_osm.py y sync_oij.py --calcular-factor sin fuente.
    if args.calcular_factor and not args.archivo:
        calcular_factor_inversion()
        return

    if not args.archivo:
        parser.error("indique --archivo, o --calcular-factor solo")

    try:
        total = procesar(args.archivo)
        print(f"OK: {total} contratos ambientales cargados desde '{args.archivo}'")
        if args.calcular_factor:
            calcular_factor_inversion()
    except Exception as exc:
        with get_connection() as conn:
            registrar_sincronizacion(conn, fuente_codigo="SICOP", estado="error", mensaje=str(exc))
        raise


if __name__ == "__main__":
    main()
