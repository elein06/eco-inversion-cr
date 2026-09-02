from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from app.config import settings


@contextmanager
def get_db_connection():
    conn = psycopg2.connect(settings.database_url)
    try:
        yield conn
    finally:
        conn.close()


def get_db():
    """Dependencia de FastAPI: entrega un cursor con resultados como dict."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            yield cursor
