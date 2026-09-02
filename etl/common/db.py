"""
Utilidades compartidas por los cuatro scripts de ETL (SNIT, SICOP, OSM, OIJ):
conexión a la base de datos y registro de cada corrida en `sincronizaciones`,
que es el mecanismo de trazabilidad y manejo de errores del proyecto.
"""
import os
from contextlib import contextmanager

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://eco_inversion:changeme@localhost:5432/eco_inversion_cr",
)


@contextmanager
def get_connection():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_fuente_id(conn, codigo: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT fuente_id FROM fuentes WHERE codigo = %s", (codigo,))
        row = cur.fetchone()
        if row is None:
            raise ValueError(
                f"Fuente '{codigo}' no existe en la tabla fuentes. "
                "Corre db/schema.sql para cargar los datos semilla."
            )
        return row[0]


def get_canton_id_por_nombre(conn, nombre: str) -> int | None:
    """Busca un canton_id por nombre, insensible a mayúsculas y tildes simples."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT canton_id FROM cantones WHERE unaccent(lower(nombre)) = unaccent(lower(%s))",
            (nombre,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def registrar_sincronizacion(
    conn,
    fuente_codigo: str,
    estado: str,
    registros_procesados: int = 0,
    mensaje: str = "",
) -> None:
    """
    Registra el resultado de una corrida de ETL en `sincronizaciones`.
    estado debe ser uno de: 'exito', 'error', 'parcial'.
    """
    fuente_id = get_fuente_id(conn, fuente_codigo)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sincronizaciones (fuente_id, estado, registros_procesados, mensaje)
            VALUES (%s, %s, %s, %s)
            """,
            (fuente_id, estado, registros_procesados, mensaje),
        )
