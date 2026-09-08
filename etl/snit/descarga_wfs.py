"""
Descarga desde los servicios WFS del SNIT — Integrante 1.

Aisla todo lo que habla con los servidores del SNIT: GetCapabilities para
confirmar que capas publica cada nodo, y GetFeature paginado para traerlas.
No sabe nada de bases de datos: devuelve features GeoJSON y ya.
"""
import os
import time

import requests
from owslib.wfs import WebFeatureService

from capas import CAPAS, NODOS, WFS_VERSION, tamanio_pagina, url_nodo

TIMEOUT_SEGUNDOS = int(os.environ.get("SNIT_WFS_TIMEOUT", "300"))
REINTENTOS = 3


def listar_capas(nodo=None):
    """Imprime las capas publicadas por cada nodo WFS del SNIT."""
    nodos = {nodo: NODOS[nodo]} if nodo else NODOS
    for nombre_nodo, url in nodos.items():
        print("\n=== {} — {} ===".format(nombre_nodo, url))
        try:
            wfs = WebFeatureService(url=url, version=WFS_VERSION)
        except Exception as exc:
            # El nodo PNE solo negocia WFS 1.1.0 en GetCapabilities, aunque
            # sí acepta GetFeature 2.0.0 con paginación.
            print("  (v{} falló: {}; reintentando con 1.1.0)".format(WFS_VERSION, exc))
            wfs = WebFeatureService(url=url, version="1.1.0")
        for nombre in sorted(wfs.contents):
            print("  {}\n      título: {}".format(nombre, wfs.contents[nombre].title))


# ------------------------------------------------------------------


def descargar_capa(nombre_capa, bbox=None):
    """
    Descarga las features de una capa en GeoJSON EPSG:4326.

    Pagina con count + startIndex de forma explícita: el nodo IGN reporta
    numberMatched=7 y devuelve 7 features por defecto aunque la capa tenga 84,
    así que el conteo del servidor no sirve como condición de parada. Se pagina
    hasta recibir una página más corta que el tamaño pedido.

    `bbox` es opcional, en formato "minlon,minlat,maxlon,maxlat". Las capas que
    usa el proyecto son chicas y se traen completas, pero el filtro espacial es
    necesario si alguien quiere trabajar con capas de mayor detalle, como
    IGN_25:caucedrenaje_25k, que tiene 118 136 features.
    """
    cfg = CAPAS[nombre_capa]
    url = url_nodo(nombre_capa)
    por_pagina = tamanio_pagina(nombre_capa)
    features = []
    inicio = 0

    while True:
        params = {
            "service": "WFS",
            "version": WFS_VERSION,
            "request": "GetFeature",
            "typeNames": cfg["typename"],
            "outputFormat": "application/json",
            "srsName": "EPSG:4326",
            "count": por_pagina,
            "startIndex": inicio,
        }
        if bbox:
            # Se declara el CRS del bbox como CRS84 y no como EPSG:4326: en
            # WFS 2.0 el EPSG:4326 usa orden latitud,longitud, mientras que
            # CRS84 usa longitud,latitud, que es el orden natural del GeoJSON
            # y evita que el filtro caiga en el lugar equivocado del planeta.
            params["bbox"] = "{},urn:ogc:def:crs:OGC:1.3:CRS84".format(bbox)
        pagina = _get_json_con_reintentos(url, params, cfg["typename"], inicio)
        lote = pagina.get("features", [])
        features.extend(lote)
        print("  ... {} features (startIndex={})".format(len(features), inicio))
        if len(lote) < por_pagina:
            break
        inicio += por_pagina

    return features


def _get_json_con_reintentos(url, params, typename, inicio):
    """GET con reintentos: los nodos del SNIT son lentos e intermitentes."""
    ultimo_error = None
    for intento in range(1, REINTENTOS + 1):
        try:
            respuesta = requests.get(url, params=params, timeout=TIMEOUT_SEGUNDOS)
            respuesta.raise_for_status()
            return respuesta.json()
        except Exception as exc:
            ultimo_error = exc
            espera = 5 * intento
            print(
                "  intento {}/{} falló en {} (startIndex={}): {}. "
                "Reintentando en {}s".format(
                    intento, REINTENTOS, typename, inicio, exc, espera
                )
            )
            time.sleep(espera)
    raise RuntimeError(
        "No se pudo descargar {} (startIndex={}) tras {} intentos: {}".format(
            typename, inicio, REINTENTOS, ultimo_error
        )
    )


# ------------------------------------------------------------------
