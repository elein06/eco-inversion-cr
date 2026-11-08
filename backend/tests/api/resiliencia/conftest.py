"""
Experimento de resiliencia con Toxiproxy (ítem 4.10, ver docs/resiliencia.md).

Toxiproxy se pone entre la API y PostgreSQL y permite meter latencia o cortar
la conexión a voluntad. La API (TestClient, en el mismo proceso) se conecta a
la base A TRAVÉS del proxy; la siembra de datos y las verificaciones de
consistencia usan la conexión DIRECTA (TEST_DATABASE_URL), que no se toca.

    docker compose -f docker-compose.yml -f docker-compose.resiliencia.yml up -d db toxiproxy
    TEST_DATABASE_URL=postgresql://eco_inversion:changeme@localhost:5432/eco_inversion_test \
    TOXIPROXY_URL=http://127.0.0.1:8474 pytest -m resiliencia -v

Sin TOXIPROXY_URL estas pruebas se omiten (skipped), no se dan por aprobadas.
"""

import os
import time
from urllib.parse import urlparse, urlunparse

import httpx
import pytest

from app.config import settings

TOXIPROXY_URL = os.environ.get("TOXIPROXY_URL")
# Desde dónde Toxiproxy alcanza a PostgreSQL. Dentro de docker-compose es el
# servicio "db"; si Toxiproxy corre fuera de Docker, localhost:5432.
UPSTREAM = os.environ.get("TOXIPROXY_UPSTREAM", "db:5432")
# Puerto donde el proxy escucha y por donde entra la API.
PUERTO_PROXY = int(os.environ.get("TOXIPROXY_PUERTO", "15432"))
PROXY = "postgres"
# Etiqueta las sesiones de la API en pg_stat_activity para poder saber,
# desde la conexión directa, cuándo una solicitud ya está conectada.
APP_NAME = "eco-api-resiliencia"


class Toxiproxy:
    """Cliente mínimo de la API REST de Toxiproxy."""

    def __init__(self, base: str):
        self.http = httpx.Client(base_url=base, timeout=5)

    def preparar(self):
        self.http.delete(f"/proxies/{PROXY}")  # 404 si no existía: da igual
        r = self.http.post(
            "/proxies",
            json={"name": PROXY, "listen": f"0.0.0.0:{PUERTO_PROXY}", "upstream": UPSTREAM},
        )
        r.raise_for_status()

    def latencia(self, ms: int, nombre: str = "latencia"):
        """Retrasa cada paquete que la base envía a la API."""
        self._toxic(nombre, "latency", {"latency": ms}, stream="downstream")

    def congelar(self, nombre: str = "congelado"):
        """La conexión sigue abierta pero no pasa ni un byte (red colgada)."""
        self._toxic(nombre, "timeout", {"timeout": 0})

    def cortar(self):
        """Corte total: el proxy rechaza conexiones y cierra las abiertas."""
        self.http.post(f"/proxies/{PROXY}", json={"enabled": False}).raise_for_status()

    def restaurar(self):
        """Quita todos los fallos y vuelve a habilitar el proxy."""
        r = self.http.get(f"/proxies/{PROXY}/toxics")
        r.raise_for_status()
        for toxic in r.json():
            self.http.delete(f"/proxies/{PROXY}/toxics/{toxic['name']}")
        self.http.post(f"/proxies/{PROXY}", json={"enabled": True}).raise_for_status()

    def _toxic(self, nombre, tipo, atributos, stream="downstream"):
        r = self.http.post(
            f"/proxies/{PROXY}/toxics",
            json={"name": nombre, "type": tipo, "stream": stream, "attributes": atributos},
        )
        r.raise_for_status()


def _url_por_el_proxy() -> str:
    """TEST_DATABASE_URL, pero entrando por el puerto del proxy."""
    original = urlparse(os.environ["TEST_DATABASE_URL"])
    host = TOXIPROXY_URL and urlparse(TOXIPROXY_URL).hostname or "127.0.0.1"
    # En Windows, "localhost" prueba primero IPv6 (::1); el proxy solo escucha
    # en 127.0.0.1 y Windows tarda ~2 s en rendirse antes de pasar a IPv4.
    # Esos 2 s se sumarían a cada medición del experimento.
    if host == "localhost":
        host = "127.0.0.1"
    netloc = f"{original.username}:{original.password}@{host}:{PUERTO_PROXY}"
    return urlunparse(original._replace(netloc=netloc, query=f"application_name={APP_NAME}"))


@pytest.fixture(scope="session")
def toxiproxy(_esquema):
    if not TOXIPROXY_URL:
        pytest.skip("TOXIPROXY_URL no definida: se omite el experimento de resiliencia")
    tp = Toxiproxy(TOXIPROXY_URL)
    try:
        tp.preparar()
    except httpx.HTTPError as exc:
        pytest.fail(f"Toxiproxy no responde en {TOXIPROXY_URL}: {exc}")
    yield tp
    tp.restaurar()


@pytest.fixture(autouse=True)
def api_por_el_proxy(toxiproxy, monkeypatch):
    """Durante cada prueba la API usa el proxy; al terminar, todo se restaura."""
    toxiproxy.restaurar()
    monkeypatch.setattr(settings, "database_url", _url_por_el_proxy())
    yield
    toxiproxy.restaurar()


def esperar_sesion_de_la_api(db, limite_s: float = 10) -> None:
    """Espera (por la conexión directa) a que la API abra su sesión en la base."""
    fin = time.monotonic() + limite_s
    while time.monotonic() < fin:
        with db.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM pg_stat_activity WHERE application_name = %s",
                (APP_NAME,),
            )
            if cur.fetchone()["n"]:
                db.rollback()
                return
        db.rollback()
        time.sleep(0.02)
    raise AssertionError("La API nunca abrió su sesión en la base")
