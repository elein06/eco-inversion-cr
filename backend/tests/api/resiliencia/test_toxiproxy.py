"""
Escenarios del experimento de resiliencia (docs/resiliencia.md, R1–R6).

Dependencia crítica: PostgreSQL. Cada prueba mete un fallo con Toxiproxy,
comprueba el comportamiento esperado y verifica la recuperación. El fixture
api_por_el_proxy restaura el proxy al terminar, falle o no la prueba.
"""

import threading
import time

import pytest

from app.config import settings

from ..conftest import PASSWORD, PESOS
from .conftest import esperar_sesion_de_la_api

pytestmark = [pytest.mark.api, pytest.mark.resiliencia]

MENSAJE_503 = "La base de datos no está disponible. Intente de nuevo."


def cronometrar(funcion):
    inicio = time.monotonic()
    r = funcion()
    return r, time.monotonic() - inicio


def contar_escenarios(db) -> int:
    with db.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM escenarios")
        n = cur.fetchone()["n"]
    db.rollback()
    return n


def assert_503_limpio(r):
    """503 con mensaje genérico: sin trazas, nombres de host ni errores de psycopg2."""
    assert r.status_code == 503, r.text
    assert r.json() == {"detail": MENSAJE_503}
    assert r.headers["Retry-After"] == "5"
    assert "X-Request-ID" in r.headers


# R1 — Base lenta pero dentro de los límites: la API responde, solo más lenta.
def test_r1_latencia_moderada_responde(client, toxiproxy):
    toxiproxy.latencia(300)
    r, segundos = cronometrar(lambda: client.get("/health/listo"))
    assert r.status_code == 200, r.text
    assert segundos >= 0.3, "la latencia no se aplicó: el experimento no es válido"
    limite = settings.db_connect_timeout
    assert segundos < limite


# R2 — Base tan lenta que la conexión no se completa a tiempo: 503 en ~5 s.
def test_r2_latencia_alta_da_503_por_connect_timeout(client, toxiproxy):
    toxiproxy.latencia(10_000)
    r, segundos = cronometrar(lambda: client.get("/health/listo"))
    assert_503_limpio(r)
    limite = settings.db_connect_timeout + 2
    assert segundos < limite


# R3 — Corte total: 503 inmediato, el proceso sigue vivo y el login no
# confunde la caída con una contraseña incorrecta (no suma intentos fallidos).
def test_r3_corte_total(client, toxiproxy, db):
    toxiproxy.cortar()

    r, segundos = cronometrar(lambda: client.get("/health/listo"))
    assert_503_limpio(r)
    assert segundos < 2

    assert client.get("/health").status_code == 200  # vivo aunque la base no

    r = client.post("/auth/login", json={"email": "ana@prueba.cr", "password": "incorrecta"})
    assert_503_limpio(r)
    with db.cursor() as cur:
        cur.execute("SELECT intentos_fallidos FROM usuarios WHERE email = 'ana@prueba.cr'")
        assert cur.fetchone()["intentos_fallidos"] == 0
    db.rollback()


# R4 — Escritura durante el corte: no queda nada guardado a medias ni
# duplicado; al volver la base, el mismo pedido se guarda una sola vez.
def test_r4_escritura_durante_el_corte_es_consistente(client, toxiproxy, db, como):
    cabeceras = como("ana")  # la sesión se obtiene antes del corte
    cuerpo = {"nombre": "Durante el corte", "pesos": PESOS, "cantones": [1, 2]}
    antes = contar_escenarios(db)

    toxiproxy.cortar()
    assert_503_limpio(client.post("/escenarios", headers=cabeceras, json=cuerpo))
    assert contar_escenarios(db) == antes

    toxiproxy.restaurar()
    r = client.post("/escenarios", headers=cabeceras, json=cuerpo)
    assert r.status_code == 201, r.text
    assert contar_escenarios(db) == antes + 1


# R5 — Recuperación automática: al quitar el fallo la API vuelve a responder
# sin reiniciar nada (cada solicitud abre su propia conexión).
def test_r5_recuperacion_automatica(client, toxiproxy):
    toxiproxy.cortar()
    assert client.get("/health/listo").status_code == 503

    toxiproxy.restaurar()
    r, segundos = cronometrar(lambda: client.get("/health/listo"))
    assert r.status_code == 200, r.text
    assert segundos < 1
    login = client.post("/auth/login", json={"email": "ana@prueba.cr", "password": PASSWORD})
    assert login.status_code == 200


# R6 — La red se congela con una solicitud YA conectada. statement_timeout no
# sirve aquí: lo aplica el servidor, y el servidor ya respondió; lo que se
# perdió es la respuesta en el camino. La API debe cortar por su cuenta.
def test_r6_red_congelada_con_solicitud_en_curso_no_cuelga(client, toxiproxy, db, monkeypatch):
    monkeypatch.setattr(settings, "db_statement_timeout_ms", 2000)
    limite = 2 + 2 + 3  # statement_timeout + margen de la API + holgura de la prueba

    # La latencia deja la solicitud "en el camino" el tiempo suficiente para
    # congelar la red justo después de que la API se conectó.
    toxiproxy.latencia(500)
    resultado = {}

    def pedir():
        resultado["r"], resultado["s"] = cronometrar(lambda: client.get("/health/listo"))

    hilo = threading.Thread(target=pedir, daemon=True)
    hilo.start()
    esperar_sesion_de_la_api(db)
    toxiproxy.congelar()

    hilo.join(timeout=limite)
    colgada = hilo.is_alive()
    toxiproxy.restaurar()  # libera la solicitud colgada, si la hay
    hilo.join(timeout=15)

    assert not colgada, f"la API quedó colgada más de {limite} s con la red congelada"
    assert_503_limpio(resultado["r"])
