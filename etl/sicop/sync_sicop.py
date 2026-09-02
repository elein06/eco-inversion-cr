"""
ETL — Integrante 2 — SICOP (inversión municipal ambiental)

Flujo:
  1. Leer un reporte descargado manualmente del módulo de datos abiertos de
     SICOP (Excel/CSV/JSON) — SICOP no ofrece una API REST limpia.
  2. Clasificar cada contrato como "ambiental" con un filtro de palabras
     clave por regex sobre la descripción del objeto contractual.
  3. Cargar los contratos ambientales en `contratos_ambientales`.

Uso:
    python sync_sicop.py --archivo reportes/contratos_2025.xlsx
"""
import argparse
import os
import re
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

import pandas as pd
from dotenv import load_dotenv

from db import get_canton_id_por_nombre, get_connection, registrar_sincronizacion  # noqa: E402

load_dotenv()

# Criterio explícito y documentado (ver docs/sicop.md) — no es machine learning.
PALABRAS_CLAVE_AMBIENTAL = [
    "residuos",
    "reciclaje",
    "arborizacion",
    "arborización",
    "alcantarillado",
    "gestion ambiental",
    "gestión ambiental",
    "infraestructura verde",
    "tratamiento de aguas",
    "reforestacion",
    "reforestación",
]
PATRON_AMBIENTAL = re.compile(
    "|".join(re.escape(p) for p in PALABRAS_CLAVE_AMBIENTAL), re.IGNORECASE
)

COLUMNAS_ESPERADAS = {
    "Institución": "institucion",
    "Municipalidad": "municipalidad",
    "Monto adjudicado": "monto",
    "Moneda": "moneda",
    "Fecha de contrato": "fecha_contrato",
    "Descripción del objeto": "descripcion_objeto",
}


def clasificar(descripcion: str) -> str | None:
    if not isinstance(descripcion, str):
        return None
    match = PATRON_AMBIENTAL.search(descripcion)
    return match.group(0).lower() if match else None


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
    parser.add_argument("--archivo", required=True, help="Ruta al reporte descargado (xlsx/csv)")
    args = parser.parse_args()

    try:
        total = procesar(args.archivo)
        print(f"OK: {total} contratos ambientales cargados desde '{args.archivo}'")
    except Exception as exc:
        with get_connection() as conn:
            registrar_sincronizacion(
                conn, fuente_codigo="SICOP", estado="error", mensaje=str(exc)
            )
        raise


if __name__ == "__main__":
    main()
