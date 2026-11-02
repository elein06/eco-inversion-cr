"""
Registro de eventos de seguridad (login fallido, acceso denegado, acciones
de administración) como líneas JSON en el logger "eco.seguridad".

Pensado para que Loki/Grafana los consulten y alerten (ítems 7.2 y 7.3):
cada línea trae evento, resultado, actor (usuario_id, nunca email ni
contraseña), IP, ruta y request_id para correlacionarla con la traza.

Nunca se registran contraseñas, tokens ni el cuerpo de la solicitud. Las
claves prohibidas se descartan aunque alguien las pase por error.
"""

import hashlib
import json
import logging
from datetime import UTC, datetime

from fastapi import Request

logger = logging.getLogger("eco.seguridad")

_CLAVES_PROHIBIDAS = {"password", "contrasena", "token", "access_token", "authorization", "jwt"}


def huella(texto: str) -> str:
    """
    Identificador estable y no reversible para un dato que no queremos en el
    log (ej. el email de un intento con una cuenta que no existe). Sirve para
    ver "10 intentos contra la misma cuenta" sin guardar la cuenta.
    """
    return hashlib.sha256(texto.strip().lower().encode()).hexdigest()[:16]


def registrar(
    evento: str,
    resultado: str,
    *,
    request: Request | None = None,
    usuario_id: int | None = None,
    **detalle: object,
) -> dict:
    registro: dict[str, object] = {
        "ts": datetime.now(UTC).isoformat(),
        "tipo": "evento_seguridad",
        "evento": evento,
        "resultado": resultado,
        "usuario_id": usuario_id,
    }
    if request is not None:
        registro["metodo"] = request.method
        registro["ruta"] = request.url.path
        registro["ip"] = request.client.host if request.client else None
        registro["request_id"] = getattr(request.state, "request_id", None)

    for clave, valor in detalle.items():
        if clave.lower() not in _CLAVES_PROHIBIDAS:
            registro[clave] = valor

    logger.info(json.dumps(registro, ensure_ascii=False, default=str))
    return registro
