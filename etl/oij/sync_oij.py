"""
ETL - Integrante 4 - Poder Judicial / OIJ (estadisticas policiales por canton)

Reemplaza a la fuente original del BCCR: no requiere token y anade una
dimension de seguridad. Sin token, publicado por el PJ, formato CSV/XLS/XML/RDF.

IMPORTANTE - formato real verificado (ver docs/oij.md, seccion "Hallazgos del
formato real"): el recurso CSV publicado en datosabiertospj.poder-judicial.go.cr
NO trae encabezado ni una columna de "Cantidad" ya agregada. Es un registro por
incidente, con 11 columnas posicionales, en codificacion latin-1 (no UTF-8):

  0 tipo_delito | 1 subtipo_delito | 2 fecha_hecho (YYYY-MM-DD) | 3 tipo_victima
  4 clasificacion_victima | 5 grupo_etario | 6 (columna reservada, vacia)
  7 nacionalidad | 8 provincia | 9 canton | 10 distrito

Por eso este script agrupa y cuenta (canton + tipo_delito + anio) antes de
cargar a `estadisticas_seguridad` - la transformacion real que pide el
enunciado del curso, no una copia directa del archivo.

Uso:
    python sync_oij.py --archivo reportes/PJCROD_POLICIALES_V1-2025.csv --anio 2025
    python sync_oij.py --resource-id <id_recurso_ckan> --anio 2025   # fallback, no confirmado para este dataset
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

# Columnas posicionales del CSV real (sin encabezado) - ver docs/oij.md
COLUMNAS_CSV = [
    "tipo_delito",
    "subtipo_delito",
    "fecha_hecho",
    "tipo_victima",
    "clasificacion_victima",
    "grupo_etario",
    "_reservada",
    "nacionalidad",
    "provincia",
    "canton",
    "distrito",
]

# Por si el recurso viniera con nombres de columna propios (poco probable, no confirmado)
RENOMBRES_DATASTORE = {
    "Canton": "canton", "Cantón": "canton",
    "Delito": "tipo_delito",
    "Fecha": "fecha_hecho", "FechaHecho": "fecha_hecho",
}

# Encodings a probar en orden - el archivo del PJ viene en latin-1, no UTF-8
ENCODINGS_A_PROBAR = ["latin-1", "cp1252", "utf-8"]


def descargar_desde_datastore(resource_id: str) -> pd.DataFrame:
    """
    Fallback si el recurso tuviera datastore activo en CKAN. NO confirmado para
    el dataset 'estadisticas-policiales': la via verificada y recomendada es
    --archivo con el CSV descargado directamente del portal (ver docs/oij.md).
    """
    url = f"{OIJ_CKAN_BASE_URL}/api/3/action/datastore_search"
    registros = []
    offset = 0
    limite = 1000
    while True:
        resp = requests.get(url, params={"resource_id": resource_id, "limit": limite, "offset": offset}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"CKAN respondio success=false: {data}")
        pagina = data["result"]["records"]
        registros.extend(pagina)
        if len(pagina) < limite:
            break
        offset += limite
    df = pd.DataFrame(registros)
    return df.rename(columns=RENOMBRES_DATASTORE)


def cargar_desde_archivo(ruta_archivo: str) -> pd.DataFrame:
    """
    Carga el CSV crudo del PJ: sin encabezado, 11 columnas posicionales,
    codificacion latin-1. Se prueban varias codificaciones por si el archivo
    cambia con el tiempo.
    """
    ultimo_error = None
    for encoding in ENCODINGS_A_PROBAR:
        try:
            df = pd.read_csv(
                ruta_archivo,
                header=None,
                names=COLUMNAS_CSV,
                encoding=encoding,
                dtype=str,
                on_bad_lines="warn",
            )
            print(f"Archivo leido con encoding='{encoding}' ({len(df)} filas crudas)")
            return df
        except (UnicodeDecodeError, UnicodeError) as exc:
            ultimo_error = exc
            continue
    raise ValueError(f"No se pudo leer el archivo con ninguna codificacion probada: {ultimo_error}")


def normalizar(df: pd.DataFrame, anio_filtro: int | None) -> pd.DataFrame:
    """
    Convierte el registro por incidente en un agregado por canton + tipo_delito
    + anio, que es lo que espera la tabla `estadisticas_seguridad`.
    """
    df = df.copy()
    for col in ("tipo_delito", "canton", "provincia"):
        df[col] = df[col].astype(str).str.strip().str.upper()

    df["fecha_hecho"] = pd.to_datetime(df["fecha_hecho"], errors="coerce")
    df["anio"] = df["fecha_hecho"].dt.year

    antes = len(df)
    df = df.dropna(subset=["canton", "tipo_delito", "anio"])
    df = df[(df["canton"] != "") & (df["canton"] != "NAN")]
    if len(df) < antes:
        print(f"Se descartaron {antes - len(df)} filas sin canton, delito o fecha valida")

    if anio_filtro:
        df = df[df["anio"] == anio_filtro]

    agregado = (
        df.groupby(["canton", "tipo_delito", "anio"], as_index=False)
        .size()
        .rename(columns={"size": "cantidad"})
    )
    agregado["anio"] = agregado["anio"].astype(int)
    return agregado


def cargar(df: pd.DataFrame) -> int:
    insertados = 0
    cantones_no_reconocidos = set()
    with get_connection() as conn:
        with conn.cursor() as cur:
            for _, fila in df.iterrows():
                canton_id = get_canton_id_por_nombre(conn, str(fila["canton"]))
                if canton_id is None:
                    cantones_no_reconocidos.add(fila["canton"])
                    continue  # canton no reconocido en `cantones` - se omite y se reporta al final
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
        if cantones_no_reconocidos:
            print(
                f"AVISO: {len(cantones_no_reconocidos)} nombre(s) de canton sin match en `cantones`: "
                f"{sorted(cantones_no_reconocidos)}"
            )
        registrar_sincronizacion(
            conn,
            fuente_codigo="OIJ",
            estado="exito" if insertados else "parcial",
            registros_procesados=insertados,
            mensaje=f"Filas agregadas procesadas: {len(df)}; cantones sin match: {len(cantones_no_reconocidos)}",
        )
    return insertados


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL OIJ (CSV crudo por incidente -> estadisticas agregadas por canton)")
    fuente = parser.add_mutually_exclusive_group(required=True)
    fuente.add_argument("--resource-id", help="ID del recurso en el datastore de CKAN (fallback, no confirmado)")
    fuente.add_argument("--archivo", help="Ruta al CSV descargado del PJ (ej. reportes/PJCROD_POLICIALES_V1-2025.csv)")
    parser.add_argument("--anio", type=int, help="Anio de referencia a filtrar (recomendado fijarlo por equipo)")
    args = parser.parse_args()

    try:
        if args.resource_id:
            df_crudo = descargar_desde_datastore(args.resource_id)
        else:
            df_crudo = cargar_desde_archivo(args.archivo)
        df = normalizar(df_crudo, args.anio)
        total = cargar(df)
        print(
            f"OK: {total} filas agregadas cargadas "
            f"({df['canton'].nunique()} cantones, {df['tipo_delito'].nunique()} tipos de delito)"
        )
    except Exception as exc:
        with get_connection() as conn:
            registrar_sincronizacion(conn, fuente_codigo="OIJ", estado="error", mensaje=str(exc))
        raise


if __name__ == "__main__":
    main()
