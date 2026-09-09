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
import os
import re
import sys

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

COLUMNAS_ESPERADAS = {
    "Institución": "institucion",
    "Municipalidad": "municipalidad",
    "Monto adjudicado": "monto",
    "Moneda": "moneda",
    "Fecha de contrato": "fecha_contrato",
    "Descripción del objeto": "descripcion_objeto",
}


def clasificar(descripcion: str) -> str | None:
    """Devuelve la categoría (una de las 6 de PALABRAS_CLAVE_AMBIENTAL) o None
    si ninguna palabra clave aparece en la descripción del objeto contractual."""
    if not isinstance(descripcion, str):
        return None
    for categoria, patron in PATRONES_POR_CATEGORIA.items():
        if patron.search(descripcion):
            return categoria
    return None


def cargar_reporte(ruta_archivo: str) -> pd.DataFrame:
    if ruta_archivo.endswith(".csv"):
        df = pd.read_csv(ruta_archivo)
    else:
        df = pd.read_excel(ruta_archivo)
    df = df.rename(columns=COLUMNAS_ESPERADAS)
    return df


def procesar(ruta_archivo: str) -> int:
    df = cargar_reporte(ruta_archivo)
    df["categoria_detectada"] = df["descripcion_objeto"].apply(clasificar)
    df_ambiental = df[df["categoria_detectada"].notna()].copy()

    insertados = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            for _, fila in df_ambiental.iterrows():
                canton_id = get_canton_id_por_nombre(conn, str(fila.get("municipalidad", "")))
                cur.execute(
                    """
                    INSERT INTO contratos_ambientales
                        (fuente_id, canton_id, institucion, municipalidad, monto,
                         moneda, fecha_contrato, descripcion_objeto, categoria_detectada)
                    VALUES (
                        (SELECT fuente_id FROM fuentes WHERE codigo = 'SICOP'),
                        %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        canton_id,
                        fila.get("institucion"),
                        fila.get("municipalidad"),
                        fila.get("monto") or 0,
                        fila.get("moneda") or "CRC",
                        fila.get("fecha_contrato"),
                        fila.get("descripcion_objeto"),
                        fila["categoria_detectada"],
                    ),
                )
                insertados += 1
        registrar_sincronizacion(
            conn,
            fuente_codigo="SICOP",
            estado="exito" if insertados else "parcial",
            registros_procesados=insertados,
            mensaje=f"Archivo: {os.path.basename(ruta_archivo)}, filas totales: {len(df)}",
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
