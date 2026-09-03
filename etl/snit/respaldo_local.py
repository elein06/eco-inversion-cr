"""
Respaldo local de las capas del SNIT — Integrante 1.

Guarda y lee la copia en disco de cada capa, con su procedencia y fecha de
consulta. Es el seguro para la demo: si el nodo del SNIT esta caido, la base
se recarga desde aqui con --desde-respaldo.
"""
import json
import os
from datetime import datetime, timezone

from capas import CAPAS, url_nodo

DIR_DATOS = os.path.join(os.path.dirname(__file__), "data")


def leer_geojson_respaldo(nombre_capa):
    """Lee la copia local de una capa, para recargar sin depender del nodo."""
    ruta = os.path.join(DIR_DATOS, "{}.geojson".format(nombre_capa))
    if not os.path.exists(ruta):
        raise FileNotFoundError(
            "No hay respaldo local de '{}' en {}. Corra primero la "
            "sincronización contra el WFS.".format(nombre_capa, ruta)
        )
    with open(ruta, encoding="utf-8") as archivo:
        return json.load(archivo)["features"]


def guardar_geojson(nombre_capa, features, bbox=None):
    """
    Guarda una copia local de la capa, con su procedencia y fecha de consulta.
    Sirve de respaldo para la demo: si el nodo del SNIT está caído el día de la
    exposición, se recarga desde aquí con --desde-respaldo.

    Una descarga filtrada por bbox va a un archivo aparte: si sobrescribiera el
    respaldo nacional, el respaldo quedaría incompleto sin que nadie lo note.
    """
    os.makedirs(DIR_DATOS, exist_ok=True)
    sufijo = "_bbox" if bbox else ""
    ruta = os.path.join(DIR_DATOS, "{}{}.geojson".format(nombre_capa, sufijo))
    coleccion = {
        "type": "FeatureCollection",
        "features": features,
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
        "metadata": {
            "fuente": "SNIT",
            "capa_wfs": CAPAS[nombre_capa]["typename"],
            "nodo": url_nodo(nombre_capa),
            "fecha_consulta": datetime.now(timezone.utc).isoformat(),
            "bbox": bbox,
            "total_features": len(features),
        },
    }
    with open(ruta, "w", encoding="utf-8") as archivo:
        json.dump(coleccion, archivo, ensure_ascii=False)
    return ruta


# ------------------------------------------------------------------
