"""
Inventario de los reportes del Módulo de Descarga de Datos (Datos Abiertos)
de SICOP, validado contra el servicio real.

Nada de este archivo se adivinó. El módulo viejo de datos abiertos
(`/moduloPcont/pcont/rp/CE_MOD_DATOSABIERTOSVIEW.jsp`) devuelve HTTP 500: SICOP
se rehizo como aplicación Angular y el módulo ahora vive en

    https://www.sicop.go.cr/app/module/pcont/public/ce-open-data

que habla con una API propia en https://prod-api.sicop.go.cr. Los códigos de
reporte (`SV_CONT_00NN`), los nombres de los campos de filtro y el formato de
las fechas se confirmaron observando las peticiones que hace ese módulo, y los
nombres de columna de cada reporte salen del Diccionario de Datos oficial que
el propio módulo publica en

    https://www.sicop.go.cr/atDocs/Diccionario_de_datos_reporte_de_contratos_de_Datos_abiertos.pdf

Ver docs/sicop.md para el detalle de la validación y la fecha de consulta.
"""
import os

from dotenv import load_dotenv

load_dotenv()

# Base de la API que consume el módulo de datos abiertos. Es pública: no pide
# token, ni cookie de sesión, ni cabecera de autenticación.
API_BASE_URL = os.environ.get("SICOP_API_BASE_URL", "https://prod-api.sicop.go.cr")

# Encola la generación de un reporte. Devuelve {reportId, status, codeReport,
# typeFile}. NO devuelve el archivo: SICOP lo construye de forma asíncrona.
URL_SOLICITAR = "{}/pcont/api/v1/public/ceOpenDataPublicController/requestDownload".format(
    API_BASE_URL
)

# Consulta si un reporte ya está construido. Devuelve texto plano: vacío
# cuando está listo, o un código de mensaje como 'msg_not_builded_report'.
URL_CONSULTAR = "{}/bid/api/v1/public/coReport/checkDownload".format(API_BASE_URL)

# Confirmacion por correo. SICOP solo construye el reporte despues de que
# alguien confirma un codigo de 6 digitos enviado a un correo electronico.
# reqCode pide el codigo; confirmCode lo valida y dispara la construccion.
URL_REQ_CODIGO = "{}/bid/api/v1/public/coConfirmCodeProc/reqCode".format(API_BASE_URL)
URL_CONFIRMAR_CODIGO = "{}/bid/api/v1/public/coConfirmCodeProc/confirmCode".format(
    API_BASE_URL
)

# Entrega el archivo ya construido. Es el mismo endpoint que usa el enlace que
# SICOP manda por correo, y solo necesita el reportId.
URL_DESCARGAR = "{}/bid/api/v1/public/coReport/download".format(API_BASE_URL)

# Página del módulo, para documentación y para el paso manual de confirmación
# por correo (ver docs/sicop.md).
URL_MODULO = os.environ.get(
    "SICOP_DATOS_ABIERTOS_URL",
    "https://www.sicop.go.cr/app/module/pcont/public/ce-open-data",
)

TIMEOUT = int(os.environ.get("SICOP_TIMEOUT", "120"))
ESPERA_MAX = int(os.environ.get("SICOP_ESPERA_MAX", "1800"))
ESPERA_INTERVALO = int(os.environ.get("SICOP_ESPERA_INTERVALO", "30"))

# Formatos que acepta el campo `typeFile` de la solicitud.
FORMATOS = ("csv", "xlsx", "json")


# ------------------------------------------------------------------
# Catálogo de reportes
#
# `usa_fechas` marca los reportes que exigen rango (startDt/endDt). Los tres
# catálogos (instituciones, proveedores, bienes y servicios) son fotos del
# estado actual y no aceptan rango.
#
# `usa` marca los tres reportes que este ETL necesita. Los otros ocho se
# dejan documentados porque son el mapa de la fuente: si en la exposición
# preguntan por qué se eligieron estos y no otros, la respuesta está aquí.
# ------------------------------------------------------------------
REPORTES = {
    "solicitudes": {
        "codigo": "SV_CONT_0008",
        "seccion": "Solicitud de contratación",
        "usa_fechas": True,
        "usa": False,
        "descripcion": (
            "Solicitudes de compra con presupuesto estimado y finalidad "
            "pública. No se usa: son intenciones de compra, no plata "
            "comprometida."
        ),
    },
    "carteles": {
        "codigo": "SV_CONT_0009",
        "seccion": "Detalle pliego de condiciones",
        "usa_fechas": True,
        "usa": True,
        "descripcion": (
            "Pliegos de condiciones (carteles). Es el ÚNICO reporte que trae "
            "la descripción en texto del objeto contractual, que es sobre la "
            "que corre el filtro de palabras clave ambientales."
        ),
    },
    "aclaraciones": {
        "codigo": "SV_CONT_0010",
        "seccion": "Aclaraciones",
        "usa_fechas": True,
        "usa": False,
        "descripcion": "Solicitudes de aclaración al cartel. No aporta al índice.",
    },
    "recursos": {
        "codigo": "SV_CONT_0011",
        "seccion": "Recursos",
        "usa_fechas": True,
        "usa": False,
        "descripcion": "Recursos de revocatoria y apelación. No aporta al índice.",
    },
    "ofertas": {
        "codigo": "SV_CONT_0012",
        "seccion": "Ofertas",
        "usa_fechas": True,
        "usa": False,
        "descripcion": "Ofertas presentadas. No aporta al índice.",
    },
    "adjudicaciones": {
        "codigo": "SV_CONT_0013",
        "seccion": "Adjudicaciones en firme",
        "usa_fechas": True,
        "usa": False,
        "descripcion": (
            "Actos de adjudicación en firme. Alternativa a 'contratos'; se "
            "prefirió el contrato porque es la etapa donde el monto queda "
            "efectivamente comprometido."
        ),
    },
    "contratos": {
        "codigo": "SV_CONT_0014",
        "seccion": "Contratos",
        "usa_fechas": True,
        "usa": True,
        "descripcion": (
            "Contratos y sus líneas. Aporta la fecha de notificación y, por "
            "línea, cantidad y precio unitario: de ahí sale el monto."
        ),
    },
    "ordenes": {
        "codigo": "SV_CONT_0015",
        "seccion": "Ordenes de pedido",
        "usa_fechas": True,
        "usa": False,
        "descripcion": (
            "Órdenes de pedido derivadas de un contrato. No se usa para no "
            "contar dos veces el mismo dinero."
        ),
    },
    "instituciones": {
        "codigo": "SV_CONT_0016",
        "seccion": "Instituciones compradoras",
        "usa_fechas": False,
        "usa": True,
        "descripcion": (
            "Catálogo de instituciones compradoras con provincia, CANTÓN y "
            "distrito. Es la pieza que permite ligar un contrato a un cantón "
            "sin adivinar a partir del nombre de la municipalidad."
        ),
    },
    "proveedores": {
        "codigo": "SV_CONT_0017",
        "seccion": "Proveedores",
        "usa_fechas": False,
        "usa": False,
        "descripcion": (
            "Catálogo de proveedores. Trae cantón, pero es el domicilio del "
            "proveedor, no el lugar de la obra: no se usa."
        ),
    },
    "catalogo": {
        "codigo": "SV_CONT_0018",
        "seccion": "Catálogo de bienes y servicios",
        "usa_fechas": False,
        "usa": False,
        "descripcion": (
            "Catálogo UNSPSC de bienes y servicios. Exige un código de "
            "clasificación de 8 dígitos, así que no se puede bajar completo."
        ),
    },
}

# Reportes que descarga `sync_sicop.py --solicitar --todos`, en el orden en que
# los necesita la normalización.
REPORTES_DEL_PROYECTO = [
    nombre for nombre, cfg in REPORTES.items() if cfg["usa"]
]


# ------------------------------------------------------------------
# Columnas esperadas por reporte, según el Diccionario de Datos oficial.
#
# Se usan para dos cosas: validar que el archivo bajado es el que creemos, y
# resolver los nombres reales de columna, que llegan en MAYÚSCULAS y a veces
# con tilde o con espacio en vez de guión bajo.
# ------------------------------------------------------------------
COLUMNAS = {
    # Reporte 2 del diccionario. La descripción del objeto contractual vive acá.
    "carteles": [
        "NRO_SICOP",
        "CEDULA_INSTITUCION",
        "FECHA_PUBLICACION",
        "NRO_PROCEDIMIENTO",
        "TIPO_PROCEDIMIENTO",
        "MODALIDAD_PROCEDIMIENTO",
        "DESCRIPCION",
    ],
    # Reporte 7 del diccionario (cabecera del contrato).
    "contratos": [
        "NRO_CONTRATO",
        "SECUENCIA",
        "NRO_SICOP",
        "NUMERO_PROCEDIMIENTO",
        "CEDULA_PROVEEDOR",
        "FECHA_NOTIFICACION",
    ],
    # Reporte 7.2 del diccionario (líneas del contrato). De acá sale el monto.
    "contratos_lineas": [
        "NRO_CONTRATO",
        "SECUENCIA",
        "NRO_LINEA_CONTRATO",
        "CANTIDAD_CONTRATADA",
        "PRECIO_UNITARIO",
        "TIPO_MONEDA",
        "DESCUENTO",
        "IVA",
        "OTROS_IMPUESTOS",
        "ACARREOS",
        "TIPO_CAMBIO_CRC",
    ],
    # Reporte 11 del diccionario.
    "instituciones": [
        "CEDULA",
        "NOMBRE_INSTITUCION",
        "PROVINCIA",
        "CANTON",
        "DISTRITO",
    ],
}


def codigo(nombre_reporte):
    """Traduce el nombre corto que usa el CLI al código SV_CONT_00NN de SICOP."""
    if nombre_reporte not in REPORTES:
        raise ValueError(
            "Reporte '{}' no existe. Disponibles: {}".format(
                nombre_reporte, ", ".join(sorted(REPORTES))
            )
        )
    return REPORTES[nombre_reporte]["codigo"]


def form_filters(nombre_reporte, formato="csv", desde=None, hasta=None):
    """
    Arma la lista `formFilters` que espera `requestDownload`.

    El módulo web construye este mismo arreglo descartando los campos vacíos y
    mandando las fechas en ISO 8601 UTC ('2026-09-02T06:00:00.000Z'), no en el
    dd/MM/yyyy que muestra en pantalla.

    `downloadFormat` va siempre en 'csv' porque así lo manda el módulo web: el
    campo que realmente decide el formato del archivo es `typeFile`.
    """
    cfg = REPORTES[nombre_reporte]
    if formato not in FORMATOS:
        raise ValueError(
            "Formato '{}' inválido. Use uno de: {}".format(formato, ", ".join(FORMATOS))
        )

    filtros = []
    if cfg["usa_fechas"]:
        if desde is None or hasta is None:
            raise ValueError(
                "El reporte '{}' ({}) exige rango de fechas.".format(
                    nombre_reporte, cfg["codigo"]
                )
            )
        filtros.append({"field": "startDt", "value": _a_iso_utc(desde)})
        filtros.append({"field": "endDt", "value": _a_iso_utc(hasta)})

    filtros.append({"field": "downloadFormat", "value": "csv"})
    filtros.append({"field": "typeFile", "value": formato})
    filtros.append({"field": "reportType", "value": cfg["codigo"]})
    return filtros


def page_request(nombre_reporte, formato="csv", desde=None, hasta=None):
    """Cuerpo completo del POST a `requestDownload`."""
    return {
        "pageNumber": 0,
        "pageSize": 100,
        "tableSorter": {"sorter": "", "order": "desc"},
        "tableFilters": [],
        "formFilters": form_filters(nombre_reporte, formato, desde, hasta),
    }


def _a_iso_utc(fecha):
    """
    Convierte un date/datetime a la cadena ISO 8601 en UTC que espera la API.
    Costa Rica es UTC-6 todo el año (no hay horario de verano), así que la
    medianoche local del día pedido es 06:00Z de ese mismo día.
    """
    if hasattr(fecha, "hour"):
        return fecha.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return fecha.strftime("%Y-%m-%dT06:00:00.000Z")
