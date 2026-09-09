"""
Cliente del Módulo de Descarga de Datos de SICOP — Integrante 2.

SICOP no entrega el archivo en la misma petición. El flujo real, tal como lo
hace el módulo web, tiene tres pasos:

    1. POST requestDownload   -> encola el reporte y devuelve un reportId
    2. POST checkDownload     -> ¿ya está construido? (texto vacío = sí)
    3. GET  download          -> entrega el archivo

Entre el paso 1 y el 2, SICOP le manda al solicitante un correo con un código
de confirmación y un enlace. Ese enlace apunta a los mismos endpoints 2 y 3 de
arriba, y por eso este script puede hacer el resto solo: lo único que no
automatiza —a propósito— es meter un correo electrónico en el formulario de
SICOP. Ver docs/sicop.md, sección "Limitación conocida".

Todo lo que se baja queda guardado en `data/` junto a un `.meta.json` con
la procedencia (endpoint, reportId, filtros, fecha de consulta), que es lo que
permite repetir la corrida y defenderla en la exposición.
"""
import json
import os
import time
from datetime import datetime, timezone

import requests

from reportes import (
    ESPERA_INTERVALO,
    ESPERA_MAX,
    REPORTES,
    TIMEOUT,
    URL_CONSULTAR,
    URL_DESCARGAR,
    URL_SOLICITAR,
    page_request,
)

DIR_DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# La API rechaza al cliente por defecto de requests. El módulo web es un
# navegador, así que se manda un User-Agent de navegador y el Origin del sitio.
CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Origin": "https://www.sicop.go.cr",
    "Referer": "https://www.sicop.go.cr/app/module/pcont/public/ce-open-data",
}

# Respuesta de checkDownload cuando el reporte todavía no existe en disco del
# lado de SICOP. Es un código de mensaje, no un error HTTP: la petición
# responde 200 con este texto en el cuerpo.
MSG_NO_CONSTRUIDO = "msg_not_builded_report"


class SicopError(RuntimeError):
    pass


def solicitar(nombre_reporte, formato="csv", desde=None, hasta=None):
    """
    Paso 1: encola el reporte. Devuelve el diccionario que responde SICOP,
    con la llave `reportId` que hace falta para los pasos 2 y 3.
    """
    cuerpo = page_request(nombre_reporte, formato, desde, hasta)
    respuesta = requests.post(
        URL_SOLICITAR, json=cuerpo, headers=CABECERAS, timeout=TIMEOUT
    )
    if respuesta.status_code != 200:
        raise SicopError(
            "requestDownload devolvió HTTP {}: {}".format(
                respuesta.status_code, respuesta.text[:300]
            )
        )
    datos = respuesta.json()
    if "reportId" not in datos:
        raise SicopError("requestDownload no devolvió reportId: {}".format(datos))

    datos["_solicitud"] = {
        "reporte": nombre_reporte,
        "codigo": REPORTES[nombre_reporte]["codigo"],
        "seccion": REPORTES[nombre_reporte]["seccion"],
        "formato": formato,
        "desde": str(desde) if desde else None,
        "hasta": str(hasta) if hasta else None,
        "endpoint": URL_SOLICITAR,
        "formFilters": cuerpo["formFilters"],
        "fecha_consulta": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return datos


def consultar(report_id):
    """
    Paso 2: pregunta si el reporte ya está construido.

    Devuelve (listo, mensaje). `listo` es True cuando SICOP responde con el
    cuerpo vacío, que es su forma de decir "ya está".
    """
    respuesta = requests.post(
        URL_CONSULTAR,
        params={"reportId": report_id},
        headers=CABECERAS,
        timeout=TIMEOUT,
    )
    if respuesta.status_code != 200:
        raise SicopError(
            "checkDownload devolvió HTTP {}: {}".format(
                respuesta.status_code, respuesta.text[:300]
            )
        )
    mensaje = respuesta.text.strip()
    return (mensaje == "", mensaje)


def esperar(report_id, espera_max=None, intervalo=None, verboso=True):
    """
    Repite el paso 2 hasta que el reporte esté listo o se agote la espera.

    No es un reintento a ciegas: SICOP construye los reportes por lotes, así
    que el tiempo depende del tamaño del rango pedido, no de la suerte.
    """
    espera_max = espera_max if espera_max is not None else ESPERA_MAX
    intervalo = intervalo if intervalo is not None else ESPERA_INTERVALO
    inicio = time.time()

    while True:
        listo, mensaje = consultar(report_id)
        if listo:
            if verboso:
                print(
                    "  reporte {} listo tras {:.0f} s".format(
                        report_id, time.time() - inicio
                    )
                )
            return True

        transcurrido = time.time() - inicio
        if transcurrido + intervalo > espera_max:
            if verboso:
                print(
                    "  reporte {} sigue en '{}' tras {:.0f} s; se agotó la "
                    "espera".format(report_id, mensaje, transcurrido)
                )
            return False

        if verboso:
            print(
                "  reporte {}: '{}' ({:.0f} s) — reintentando en {} s".format(
                    report_id, mensaje, transcurrido, intervalo
                )
            )
        time.sleep(intervalo)


def descargar(report_id, nombre_reporte=None, formato="csv", metadatos=None):
    """
    Paso 3: baja el archivo ya construido y lo guarda en `data/`.

    Devuelve la ruta del archivo guardado. Respeta el nombre que manda SICOP
    en Content-Disposition cuando viene, porque incluye el rango de fechas.
    """
    respuesta = requests.get(
        URL_DESCARGAR,
        params={"reportId": report_id},
        headers=CABECERAS,
        timeout=TIMEOUT,
        stream=True,
    )
    if respuesta.status_code != 200:
        raise SicopError(
            "download devolvió HTTP {} para reportId={}: {}".format(
                respuesta.status_code, report_id, respuesta.text[:300]
            )
        )

    # Si SICOP contesta JSON de error en vez del archivo, el cuerpo empieza con
    # '{"id":...,"status":"INTERNAL_SERVER_ERROR"'. Vale detectarlo antes de
    # guardar un archivo corrupto con nombre de reporte.
    contenido = respuesta.content
    if contenido[:1] == b"{" and b"INTERNAL_SERVER_ERROR" in contenido[:400]:
        raise SicopError(
            "download devolvió un error de SICOP en vez del archivo: {}".format(
                contenido[:300].decode("utf-8", "replace")
            )
        )

    os.makedirs(DIR_DATOS, exist_ok=True)
    nombre = _nombre_archivo(respuesta, report_id, nombre_reporte, formato)
    ruta = os.path.join(DIR_DATOS, nombre)
    with open(ruta, "wb") as archivo:
        archivo.write(contenido)

    meta = {
        "reportId": report_id,
        "endpoint_descarga": URL_DESCARGAR,
        "bytes": len(contenido),
        "content_type": respuesta.headers.get("Content-Type"),
        "content_disposition": respuesta.headers.get("Content-Disposition"),
        "fecha_descarga": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if metadatos:
        meta.update(metadatos)
    with open(ruta + ".meta.json", "w", encoding="utf-8") as archivo:
        json.dump(meta, archivo, ensure_ascii=False, indent=2)

    return ruta


def bajar_reporte(
    nombre_reporte, formato="csv", desde=None, hasta=None, espera_max=None
):
    """
    Los tres pasos en uno: solicitar, esperar y descargar.

    Devuelve (ruta, report_id). Si la espera se agota, devuelve (None,
    report_id) para que quien llama pueda reintentar después con
    `--descargar --report-id`, sin volver a encolar el reporte.
    """
    datos = solicitar(nombre_reporte, formato, desde, hasta)
    report_id = datos["reportId"]
    print(
        "  solicitado {} ({}) -> reportId={} status={}".format(
            nombre_reporte, datos.get("codeReport"), report_id, datos.get("status")
        )
    )

    if not esperar(report_id, espera_max=espera_max):
        return (None, report_id)

    ruta = descargar(
        report_id, nombre_reporte, formato, metadatos=datos.get("_solicitud")
    )
    print("  guardado: {}".format(ruta))
    return (ruta, report_id)


def _nombre_archivo(respuesta, report_id, nombre_reporte, formato):
    disposicion = respuesta.headers.get("Content-Disposition") or ""
    for parte in disposicion.split(";"):
        parte = parte.strip()
        if parte.lower().startswith("filename="):
            nombre = parte.split("=", 1)[1].strip().strip('"')
            if nombre:
                return "{}_{}".format(report_id, os.path.basename(nombre))
    base = nombre_reporte or "reporte"
    return "sicop_{}_{}.{}".format(base, report_id, formato)
