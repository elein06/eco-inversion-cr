from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from app.config import settings


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
