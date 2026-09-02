"""
ETL — Integrante 4 — Poder Judicial / OIJ (estadísticas policiales por cantón)

Reemplaza a la fuente original del BCCR: no requiere token y añade una
dimensión de seguridad. Sin token, sobre CKAN, con recursos en CSV/XLS/XML/RDF.

Flujo:
  1. Descargar un recurso CKAN (por archivo directo o vía datastore_search).
  2. Limpiar con pandas y normalizar nombre de cantón / tipo de delito / año.
  3. Cargar en `estadisticas_seguridad` (agregado por cantón, nunca por persona).

IMPORTANTE (ver docs/oij.md): estas son estadísticas agregadas. El sistema
nunca debe insinuar que un cantón "peligroso" implica algo sobre sus
habitantes, y la correlación con el índice de viabilidad no es causalidad.

Uso:
    python sync_oij.py --resource-id <id_recurso_ckan> --anio 2024
    python sync_oij.py --archivo reportes/estadisticas_2024.csv --anio 2024
"""
import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

import pandas as pd
import requests
from dotenv import load_dotenv

from db import get_canton_id_por_nombre, get_connection, registrar_sincronizacion  # noqa: E402

load_dotenv()

OIJ_CKAN_BASE_URL = os.environ.get(
    "OIJ_CKAN_BASE_URL", "https://datosabiertospj.poder-judicial.go.cr"
)

COLUMNAS_ESPERADAS = {
    "Canton": "canton",
    "Cantón": "canton",
    "Delito": "tipo_delito",
    "Cantidad": "cantidad",
    "Anio": "anio",
    "Año": "anio",
}


def descargar_desde_datastore(resource_id: str) -> pd.DataFrame:
    url = f"{OIJ_CKAN_BASE_URL}/api/3/action/datastore_search"
    registros = []
    offset = 0
    limite = 1000
    while True:
        resp = requests.get(url, params={"resource_id": resource_id, "limit": limite, "offset": offset}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"CKAN respondió success=false: {data}")
        pagina = data["result"]["records"]
        registros.extend(pagina)
        if len(pagina) < limite:
            break
        offset += limite
    return pd.DataFrame(registros)


def cargar_desde_archivo(ruta_archivo: str) -> pd.DataFrame:
    if ruta_archivo.endswith(".csv"):
        return pd.read_csv(ruta_archivo)
    return pd.read_excel(ruta_archivo)


def normalizar(df: pd.DataFrame, anio_filtro: int | None) -> pd.DataFrame:
    df = df.rename(columns=COLUMNAS_ESPERADAS)
    columnas_requeridas = {"canton", "tipo_delito", "cantidad", "anio"}
    faltantes = columnas_requeridas - set(df.columns)
    if faltantes:
        raise ValueError(f"Columnas faltantes en el recurso OIJ: {faltantes}")

    df["anio"] = pd.to_numeric(df["anio"], errors="coerce").astype("Int64")
    df["cantidad"] = pd.to_numeric(df["cantidad"], errors="coerce").fillna(0).astype(int)
    if anio_filtro:
        df = df[df["anio"] == anio_filtro]
    return df.dropna(subset=["canton", "tipo_delito", "anio"])


def cargar(df: pd.DataFrame) -> int:
    insertados = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            for _, fila in df.iterrows():
                canton_id = get_canton_id_por_nombre(conn, str(fila["canton"]))
                if canton_id is None:
                    continue  # cantón no reconocido — se omite y queda fuera del conteo
                cur.execute(
                    """
                    INSERT INTO estadisticas_seguridad
                        (fuente_id, canton_id, tipo_delito, cantidad, anio)
                    VALUES (
                        (SELECT fuente_id FROM fuentes WHERE codigo = 'OIJ'),
                        %s, %s, %s, %s
                    )
                    ON CONFLICT (canton_id, tipo_delito, anio) DO UPDATE
                        SET cantidad = EXCLUDED.cantidad,
                            fecha_consulta = now()
                    """,
                    (canton_id, fila["tipo_delito"], int(fila["cantidad"]), int(fila["anio"])),
                )
                insertados += 1
        registrar_sincronizacion(
            conn,
            fuente_codigo="OIJ",
            estado="exito" if insertados else "parcial",
            registros_procesados=insertados,
            mensaje=f"Filas totales procesadas: {len(df)}",
        )
    return insertados


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL OIJ (CKAN → estadísticas de seguridad agregadas)")
    fuente = parser.add_mutually_exclusive_group(required=True)
    fuente.add_argument("--resource-id", help="ID del recurso en el datastore de CKAN")
    fuente.add_argument("--archivo", help="Ruta a un recurso descargado (csv/xlsx)")
    parser.add_argument("--anio", type=int, help="Año de referencia a filtrar (recomendado fijarlo por equipo)")
    args = parser.parse_args()

    try:
        df_crudo = (
            descargar_desde_datastore(args.resource_id) if args.resource_id else cargar_desde_archivo(args.archivo)
        )
        df = normalizar(df_crudo, args.anio)
        total = cargar(df)
        print(f"OK: {total} filas de estadísticas de seguridad cargadas")
    except Exception as exc:
        with get_connection() as conn:
            registrar_sincronizacion(conn, fuente_codigo="OIJ", estado="error", mensaje=str(exc))
        raise


if __name__ == "__main__":
    main()
