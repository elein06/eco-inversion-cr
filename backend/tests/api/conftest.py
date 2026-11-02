"""
Ambiente de pruebas de API contra PostgreSQL + PostGIS reales.

    TEST_DATABASE_URL=postgresql://eco_inversion:changeme@localhost:5432/eco_inversion_test pytest

Por seguridad, el nombre de la base DEBE terminar en "_test": la sesión
borra y recrea el esquema completo. Si TEST_DATABASE_URL no está definida,
estas pruebas se omiten (y pytest lo reporta como "skipped", no como aprobado).

Datos ficticios: tres cantones con geometrías simples y un índice
precalculado. Cuentas: admin, ana y beto (usuarios normales).
"""

import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
import pytest

RAIZ = Path(__file__).resolve().parents[3]
URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.api

PASSWORD = "contraseña-de-prueba-123"

CANTONES = [
    # canton_id, codigo, nombre, provincia, factores (amb, inv, con, seg), indice oficial
    (1, "101", "Cantón Alfa", "San José", (80, 40, 60, 20), 50.0),
    (2, "102", "Cantón Beta", "Alajuela", (20, 90, 30, 70), 52.5),
    # Nombre malicioso a propósito: prueba la protección contra inyección en el CSV.
    (3, "103", '=HYPERLINK("http://x")', "Cartago", (50, 50, 50, 50), 50.0),
]


def _conectar():
    return psycopg2.connect(URL, cursor_factory=psycopg2.extras.RealDictCursor)


@pytest.fixture(scope="session", autouse=True)
def _esquema():
    if not URL:
        pytest.skip("TEST_DATABASE_URL no definida: se omiten las pruebas de API")
    nombre_base = urlparse(URL).path.lstrip("/")
    if not nombre_base.endswith("_test"):
        pytest.exit(
            f"TEST_DATABASE_URL apunta a '{nombre_base}', que no termina en _test. "
            "Abortado para no borrar una base real."
        )

    conn = _conectar()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
        cur.execute((RAIZ / "db" / "schema.sql").read_text(encoding="utf-8"))
        cur.execute((RAIZ / "db" / "02_usuarios_escenarios.sql").read_text(encoding="utf-8"))
        for cid, codigo, nombre, provincia, _factores, _total in CANTONES:
            x = cid * 0.1
            cur.execute(
                """
                INSERT INTO cantones (canton_id, codigo_ine, nombre, provincia, poblacion, geom)
                VALUES (%s, %s, %s, %s, 1000,
                        ST_Multi(ST_MakeEnvelope(%s, 9.0, %s, 9.1, 4326)))
                """,
                (cid, codigo, nombre, provincia, -84 + x, -84 + x + 0.05),
            )
    conn.close()
    yield


@pytest.fixture()
def db():
    conn = _conectar()
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture(autouse=True)
def usuarios(db):
    """Índice y cuentas limpios en cada prueba: admin, ana, beto."""
    from app.auth import hashear_password

    h = hashear_password(PASSWORD)
    with db.cursor() as cur:
        # El índice se repone en cada prueba: /recalcular (como admin) lo
        # sobrescribe y no debe afectar a las pruebas siguientes.
        cur.execute("DELETE FROM indice_viabilidad")
        for cid, _c, _n, _p, (fa, fi, fc, fs), total in CANTONES:
            cur.execute(
                """
                INSERT INTO indice_viabilidad
                    (canton_id, factor_ambiental, factor_inversion, factor_conectividad,
                     factor_seguridad, indice_total, pesos_usados, fecha_calculo)
                VALUES (%s, %s, %s, %s, %s, %s, '{"ambiental":0.25}', '2026-01-01T00:00:00Z')
                """,
                (cid, fa, fi, fc, fs, total),
            )
        cur.execute("TRUNCATE escenarios, usuarios RESTART IDENTITY CASCADE")
        ids = {}
        for email, rol in [
            ("admin@prueba.cr", "admin"),
            ("ana@prueba.cr", "usuario"),
            ("beto@prueba.cr", "usuario"),
        ]:
            cur.execute(
                "INSERT INTO usuarios (email, password_hash, rol) VALUES (%s, %s, %s) "
                "RETURNING usuario_id",
                (email, h, rol),
            )
            ids[email.split("@")[0]] = cur.fetchone()["usuario_id"]
    db.commit()
    return ids


@pytest.fixture(scope="session")
def client(_esquema):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def login(client, quien: str) -> dict:
    r = client.post("/auth/login", json={"email": f"{quien}@prueba.cr", "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def como(client):
    """como('ana') -> cabeceras con sesión de ana."""
    return lambda quien: login(client, quien)


PESOS = {"ambiental": 0.4, "inversion": 0.1, "conectividad": 0.3, "seguridad": 0.2}


@pytest.fixture()
def escenario_de_ana(client, como):
    r = client.post(
        "/escenarios",
        headers=como("ana"),
        json={
            "nombre": "Ecoturismo norte",
            "descripcion": "privado",
            "pesos": PESOS,
            "cantones": [1, 2, 3],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()
