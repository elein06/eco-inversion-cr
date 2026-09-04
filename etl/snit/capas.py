"""
Inventario de capas WFS del SNIT validado con GetCapabilities.

Los nombres y nodos de este archivo NO se adivinaron: se confirmaron ejecutando
`python sync_snit.py --listar-capas` contra cada nodo. Ver docs/snit.md para el
detalle de la validación y la fecha de consulta.

Hallazgo importante: las capas del SINAC (áreas silvestres protegidas y
corredores biológicos) no están publicadas en geos.snitcr.go.cr, donde el
servicio WFS está deshabilitado para ese nodo. Se publican en el nodo del
Patrimonio Natural del Estado, geos1pne.sirefor.go.cr.
"""
import os

from dotenv import load_dotenv

load_dotenv()

# Nodos WFS del SNIT usados por el proyecto.
NODOS = {
    "IGN_5_CO": os.environ.get(
        "SNIT_WFS_IGN_5_CO_URL", "https://geos.snitcr.go.cr/be/IGN_5_CO/wfs"
    ),
    "IGN_200": os.environ.get(
        "SNIT_WFS_IGN_200_URL", "https://geos.snitcr.go.cr/be/IGN_200/wfs"
    ),
    "PNE": os.environ.get("SNIT_WFS_PNE_URL", "https://geos1pne.sirefor.go.cr/wfs"),
}

WFS_VERSION = os.environ.get("SNIT_WFS_VERSION", "2.0.0")

# Paginación: el nodo IGN reporta numberMatched=7 y devuelve solo 7 features
# por defecto, aunque la capa tenga 84. La única forma de traerlas todas es
# paginar explícitamente con count + startIndex hasta recibir una página
# incompleta. No confiar en numberMatched.
#
# El tamaño de página se fija por capa, no global: la geometría cantonal viene
# a escala 1:5mil y pesa cerca de 440 KB por cantón, así que páginas grandes
# hacen que el nodo agote el tiempo de espera. La hidrografía, en cambio, son
# líneas livianas y admite páginas de 500.
TAMANIO_PAGINA = int(os.environ.get("SNIT_WFS_PAGINA", "0"))

# Capas objetivo. `destino` indica en qué tabla se carga cada una.
CAPAS = {
    "cantones": {
        "nodo": "IGN_5_CO",
        "typename": "IGN_5_CO:limitecantonal_5k",
        "destino": "cantones",
        "pagina": 25,
        "descripcion": (
            "Límite Cantonal 1:5mil (IGN) — 84 cantones. Es la unidad "
            "territorial común contra la que se cruzan las cuatro fuentes."
        ),
    },
    "area_protegida": {
        "nodo": "PNE",
        "typename": "PNE:areas_silvestres_protegidas",
        "destino": "capas_snit",
        "campo_nombre": "nombre_asp",
        "pagina": 50,
        "descripcion": (
            "Áreas Silvestres Protegidas (SINAC) — 174 features. Incluye "
            "áreas marinas, que se filtran al calcular el Factor Ambiental."
        ),
    },
    "corredor_biologico": {
        "nodo": "PNE",
        "typename": "PNE:corredoresbiologicos",
        "destino": "capas_snit",
        "campo_nombre": "nombre_cb",
        "pagina": 50,
        "descripcion": (
            "Corredores Biológicos (SINAC, Programa Nacional de Corredores "
            "Biológicos) — 151 features."
        ),
    },
    "hidrografia": {
        "nodo": "IGN_200",
        "typename": "IGN_200:reddrenaje_200k",
        "destino": "capas_snit",
        "campo_nombre": "nombre",
        "pagina": 500,
        "descripcion": (
            "Red de Drenaje 1:200mil (IGN) — 6 331 líneas. Se prefiere sobre "
            "IGN_25:caucedrenaje_25k, que tiene 118 136 features y es inviable "
            "de descargar y cruzar en el tiempo del proyecto."
        ),
    },
}


def url_nodo(nombre_capa):
    """URL del nodo WFS donde vive la capa."""
    return NODOS[CAPAS[nombre_capa]["nodo"]]


def tamanio_pagina(nombre_capa):
    """Tamaño de página de la capa. SNIT_WFS_PAGINA lo sobreescribe si se define."""
    if TAMANIO_PAGINA:
        return TAMANIO_PAGINA
    return CAPAS[nombre_capa].get("pagina", 50)
