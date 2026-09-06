"""
Confirmación por correo de una descarga de SICOP — Integrante 2.

SICOP no construye el reporte con solo encolarlo. Antes exige confirmar un
código que manda a un correo electrónico: 6-7 caracteres alfanuméricos que
distinguen mayúsculas (ejemplo real: `Lw45ef`), no dígitos. Ese es el único
paso de todo el ETL que necesita un dato personal, y por eso vive aparte y
solo corre cuando quien ejecuta el script pasa su propio correo con `--correo`.

El correo no dice a qué reporte pertenece el código, así que `adivinar_reporte`
lo prueba contra las solicitudes pendientes. Ver docs/sicop.md.

Son dos llamadas:

    POST coConfirmCodeProc/reqCode      email + processId + processType
                                        -> devuelve confirmId y manda el correo
    POST coConfirmCodeProc/confirmCode  code + confirmId + processId + processType
                                        -> valida el código y dispara la
                                           construcción del reporte

El confirmId se guarda en `data/<reportId>.confirm.json` para no tener que
copiarlo a mano entre los dos comandos.
"""
import json
import os
from datetime import datetime, timezone

import requests

from descarga_sicop import CABECERAS, DIR_DATOS, SicopError
from reportes import TIMEOUT, URL_CONFIRMAR_CODIGO, URL_REQ_CODIGO


def _page_request(form_filters):
    """
    Mismo envoltorio que usa el módulo web: pageSize 10 en el diálogo de
    confirmación, y los campos vacíos se descartan antes de mandarlos.
    """
    return {
        "pageNumber": 0,
        "pageSize": 10,
        "tableSorter": {"sorter": "", "order": "desc"},
        "tableFilters": [],
        "formFilters": [
            {"field": campo, "value": valor}
            for campo, valor in form_filters
            if valor not in (None, "")
        ],
    }


def _ruta_confirmacion(report_id):
    return os.path.join(DIR_DATOS, "{}.confirm.json".format(report_id))


def solicitar_codigo(report_id, code_report, correo, solicitud=None):
    """
    Pide a SICOP que mande el código de confirmación al correo indicado.
    Devuelve el confirmId, que hace falta para el segundo paso.

    `solicitud` es lo que devolvió `descarga_sicop.solicitar` en su llave
    `_solicitud`: reporte, formato, rango de fechas y filtros exactos. Se
    guarda junto al confirmId para que la descarga posterior pueda dejar
    esa procedencia en el `.meta.json`, aunque ocurra en otra corrida.
    """
    cuerpo = _page_request(
        [
            ("email", correo),
            ("processId", report_id),
            ("processType", code_report),
        ]
    )
    respuesta = requests.post(
        URL_REQ_CODIGO, json=cuerpo, headers=CABECERAS, timeout=TIMEOUT
    )
    if respuesta.status_code != 200:
        raise SicopError(
            "reqCode devolvió HTTP {}: {}".format(
                respuesta.status_code, respuesta.text[:300]
            )
        )
    datos = respuesta.json()
    confirm_id = datos.get("confirmId")
    if not confirm_id:
        raise SicopError("reqCode no devolvió confirmId: {}".format(datos))

    os.makedirs(DIR_DATOS, exist_ok=True)
    # El correo NO se guarda: no hace falta para el segundo paso y no tiene por
    # qué quedar escrito en el repositorio de nadie.
    with open(_ruta_confirmacion(report_id), "w", encoding="utf-8") as archivo:
        json.dump(
            {
                "reportId": report_id,
                "codeReport": code_report,
                "confirmId": confirm_id,
                "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                # Procedencia de la solicitud (sin el correo, que no se guarda).
                "solicitud": solicitud or {},
            },
            archivo,
            indent=2,
        )
    return confirm_id


def confirmar_codigo(report_id, code_report, codigo, confirm_id=None):
    """
    Manda el código que llegó por correo. Al validarlo, SICOP empieza a
    construir el reporte, y a partir de ahí `descarga_sicop.esperar` puede
    hacer el resto sin intervención.
    """
    if confirm_id is None:
        confirm_id = leer_confirm_id(report_id)
    if confirm_id is None:
        raise SicopError(
            "No hay confirmId guardado para el reporte {}. Corra primero "
            "--confirmar --correo <su correo>.".format(report_id)
        )

    cuerpo = _page_request(
        [
            ("code", str(codigo).strip()),
            ("processId", report_id),
            ("processType", code_report),
            ("confirmId", confirm_id),
        ]
    )
    respuesta = requests.post(
        URL_CONFIRMAR_CODIGO, json=cuerpo, headers=CABECERAS, timeout=TIMEOUT
    )
    if respuesta.status_code != 200:
        raise SicopError(
            "confirmCode devolvió HTTP {}: {}".format(
                respuesta.status_code, respuesta.text[:300]
            )
        )
    return True


def adivinar_reporte(codigo):
    """
    Prueba un código contra todas las solicitudes pendientes y devuelve la que
    lo acepta, o None.

    Hace falta porque el correo de SICOP no dice a qué reporte pertenece el
    código: llega con el asunto "Código verificación para reporte", sin enlace
    y sin el número de reporte. Y cuando se piden los tres reportes seguidos,
    los tres correos llegan con segundos de diferencia, así que la hora tampoco
    desempata.

    Probar no es adivinar a ciegas: el `confirmId` que se guardó al pedir cada
    código es lo que ata ese código a ese reporte, de modo que SICOP acepta
    exactamente una combinación y rechaza las demás. Son a lo sumo tres
    intentos.
    """
    for solicitud in listar_pendientes():
        if solicitud.get("descargado"):
            continue
        report_id = solicitud["reportId"]
        try:
            confirmar_codigo(
                report_id,
                solicitud["codeReport"],
                codigo,
                confirm_id=solicitud["confirmId"],
            )
            return solicitud
        except SicopError:
            continue
    return None


def leer_solicitud(report_id):
    """
    Devuelve lo que se guardó al pedir el código: reportId, codeReport,
    confirmId y fecha. Es lo que permite confirmar sin tener que acordarse de
    qué reporte era cada número.
    """
    ruta = _ruta_confirmacion(report_id)
    if not os.path.exists(ruta):
        return None
    with open(ruta, encoding="utf-8") as archivo:
        return json.load(archivo)


def listar_pendientes():
    """
    Lista las solicitudes que quedaron esperando confirmación, leyendo los
    `data/<reportId>.confirm.json`. Sirve para saber qué reportId corresponde a
    qué reporte sin depender de haber guardado la salida de la terminal.
    """
    if not os.path.isdir(DIR_DATOS):
        return []

    pendientes = []
    for nombre in os.listdir(DIR_DATOS):
        if not nombre.endswith(".confirm.json"):
            continue
        with open(os.path.join(DIR_DATOS, nombre), encoding="utf-8") as archivo:
            datos = json.load(archivo)
        # Si ya existe un archivo de datos para ese reportId, el reporte se
        # bajó y la solicitud dejó de estar pendiente.
        report_id = datos.get("reportId")
        ya_bajado = any(
            otro.startswith("{}_".format(report_id))
            or "_{}.".format(report_id) in otro
            for otro in os.listdir(DIR_DATOS)
            if not otro.endswith((".confirm.json", ".meta.json"))
        )
        datos["descargado"] = ya_bajado
        pendientes.append(datos)

    return sorted(pendientes, key=lambda d: d.get("fecha", ""))


def leer_confirm_id(report_id):
    ruta = _ruta_confirmacion(report_id)
    if not os.path.exists(ruta):
        return None
    with open(ruta, encoding="utf-8") as archivo:
        return json.load(archivo).get("confirmId")
