import select
import time
from contextlib import contextmanager

import psycopg2
import psycopg2.extensions
import psycopg2.extras

from app.config import settings

# Margen sobre statement_timeout antes de que la API deje de esperar una
# respuesta: el servidor ya habría cancelado la consulta, así que pasado este
# punto lo que falla es la red, no la consulta.
MARGEN_RESPUESTA_S = 2


class BaseSinRespuesta(psycopg2.OperationalError):
    """La base dejó de responder a mitad de una operación (red congelada)."""


def _esperar_con_limite(conn):
    """
    Límite de espera del lado del CLIENTE (hallazgo del experimento R6, ver
    docs/resiliencia.md). statement_timeout lo aplica el servidor: si la red
    se congela después de conectar, el servidor ya respondió y la respuesta
    se pierde en el camino, así que psycopg2 esperaría para siempre.

    psycopg2 llama a esta función en cada operación (conectar, consulta,
    commit) en lugar de bloquearse por su cuenta. Si se agota el plazo se
    lanza BaseSinRespuesta, que es un OperationalError: main.py la convierte
    en el mismo 503 de siempre y get_db_connection cierra la conexión.
    """
    conectando = conn.status == psycopg2.extensions.STATUS_SETUP
    plazo = (
        settings.db_connect_timeout
        if conectando
        else settings.db_statement_timeout_ms / 1000 + MARGEN_RESPUESTA_S
    )
    fin = time.monotonic() + plazo
    while True:
        estado = conn.poll()
        if estado == psycopg2.extensions.POLL_OK:
            return
        restante = fin - time.monotonic()
        if restante <= 0:
            raise BaseSinRespuesta(f"la base no respondió en {plazo:g} s")
        if estado == psycopg2.extensions.POLL_READ:
            select.select([conn.fileno()], [], [], restante)
        elif estado == psycopg2.extensions.POLL_WRITE:
            select.select([], [conn.fileno()], [], restante)
        else:
            raise psycopg2.OperationalError(f"estado de poll inesperado: {estado}")


psycopg2.extensions.set_wait_callback(_esperar_con_limite)


@contextmanager
def get_db_connection():
    # connect_timeout: cuánto esperar a que la base acepte la conexión.
    # statement_timeout: tope por consulta, para que una consulta trabada no
    # retenga la conexión para siempre. Si se exceden, psycopg2 lanza
    # OperationalError / QueryCanceled y main.py lo convierte en un 503.
    conn = psycopg2.connect(
        settings.database_url,
        connect_timeout=settings.db_connect_timeout,
        options=f"-c statement_timeout={settings.db_statement_timeout_ms}",
    )
    try:
        yield conn
    finally:
        conn.close()


def get_db():
    """Dependencia de FastAPI: entrega un cursor con resultados como dict."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            yield cursor
