"""
Experimento de carga con corte de la base (ítem 4.10, ver docs/resiliencia.md).

Lanza Artillery contra la API durante 60 s y, mientras tanto, usa Toxiproxy:

    0–20 s   normal
    20–40 s  corte total de PostgreSQL
    40–60 s  base restaurada (recuperación)

Al terminar deja en resiliencia/resultados/:
    carga-<fecha>.json         reporte completo de Artillery
    carga-<fecha>-linea.txt    cuándo se cortó y restauró la base
    carga-<fecha>-resumen.md   respuestas y latencia por cada 10 s

Requisitos: Toxiproxy corriendo (docker-compose.resiliencia.yml), la API
corriendo y conectada A TRAVÉS del proxy, y Artillery instalado una vez con
la versión fijada en resiliencia/package-lock.json. Solo usa la biblioteca
estándar de Python.

    npm ci --prefix resiliencia
    python resiliencia/experimento_carga.py
"""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RESULTADOS = AQUI / "resultados"
API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")
TOXIPROXY_URL = os.environ.get("TOXIPROXY_URL", "http://127.0.0.1:8474")
UPSTREAM = os.environ.get("TOXIPROXY_UPSTREAM", "db:5432")
# Instalado con `npm ci --prefix resiliencia` (versión fijada en package-lock.json).
ARTILLERY = AQUI / "node_modules" / ".bin" / ("artillery.cmd" if os.name == "nt" else "artillery")
CORTE_EN_S, RESTAURAR_EN_S = 20, 40


def toxiproxy(metodo: str, ruta: str, cuerpo: dict | None = None) -> int:
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    pedido = urllib.request.Request(  # noqa: S310 (URL local fija)
        TOXIPROXY_URL + ruta, data=datos, method=metodo
    )
    pedido.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(pedido, timeout=5) as r:  # noqa: S310 (URL local fija)
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def preparar_proxy():
    toxiproxy("DELETE", "/proxies/postgres")
    estado = toxiproxy(
        "POST",
        "/proxies",
        {"name": "postgres", "listen": "0.0.0.0:15432", "upstream": UPSTREAM},
    )
    if estado not in (200, 201):
        sys.exit(f"No se pudo crear el proxy en {TOXIPROXY_URL} (HTTP {estado})")


def comprobar_api():
    try:
        with urllib.request.urlopen(API_URL + "/health/listo", timeout=10) as r:  # noqa: S310
            if r.status == 200:
                return
    except Exception as e:  # noqa: BLE001
        sys.exit(
            f"La API no está lista en {API_URL}/health/listo: {e}\n"
            "¿Está corriendo uvicorn en otra terminal, con DATABASE_URL apuntando al puerto 15432?"
        )


def linea_de_tiempo(registro: list[str]):
    inicio = time.monotonic()

    def marcar(texto):
        ahora = datetime.now().isoformat(timespec="seconds")
        registro.append(f"{ahora}  +{time.monotonic() - inicio:5.1f}s  {texto}")
        print(registro[-1], flush=True)

    marcar("Artillery inició la carga (base normal)")
    time.sleep(CORTE_EN_S)
    toxiproxy("POST", "/proxies/postgres", {"enabled": False})
    marcar("CORTE: proxy deshabilitado, la API no alcanza a PostgreSQL")
    time.sleep(RESTAURAR_EN_S - CORTE_EN_S)
    toxiproxy("POST", "/proxies/postgres", {"enabled": True})
    marcar("RESTAURADO: proxy habilitado de nuevo")


def resumir(reporte: Path, linea: list[str]) -> str:
    datos = json.loads(reporte.read_text(encoding="utf-8"))
    filas = []
    inicio = None
    for bloque in datos.get("intermediate", []):
        c = bloque.get("counters", {})
        t = int(bloque.get("period", 0)) / 1000
        inicio = inicio or t
        lat = bloque.get("summaries", {}).get("http.response_time", {})
        errores = sum(v for k, v in c.items() if k.startswith("errors."))
        filas.append(
            f"| {t - inicio:>4.0f}–{t - inicio + 10:.0f} s "
            f"| {c.get('http.codes.200', 0)} | {c.get('http.codes.503', 0)} | {errores} "
            f"| {lat.get('p95', '-')} | {lat.get('max', '-')} |"
        )
    total = datos.get("aggregate", {}).get("counters", {})
    return "\n".join(
        [
            "# Experimento de carga con corte de la base",
            "",
            f"Reporte: `{reporte.name}`",
            "",
            "## Línea de tiempo",
            "",
            "```",
            *linea,
            "```",
            "",
            "## Respuestas por ventana de 10 s",
            "",
            "| Ventana | 200 | 503 | Errores de red/timeout | p95 ms | máx ms |",
            "|---|---|---|---|---|---|",
            *filas,
            "",
            f"Total: {total.get('http.requests', 0)} solicitudes, "
            f"{total.get('http.codes.200', 0)} con 200, {total.get('http.codes.503', 0)} con 503.",
            "",
            "Las ventanas son de Artillery y no coinciden exactamente con los segundos",
            "del corte; compárelas con la línea de tiempo.",
            "",
        ]
    )


def main():
    if not ARTILLERY.exists():
        sys.exit(
            "Falta Artillery. Instálelo una vez (necesita Node.js), desde la raíz del repo:\n"
            "    npm ci --prefix resiliencia"
        )
    RESULTADOS.mkdir(exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d-%H%M%S")
    reporte = RESULTADOS / f"carga-{sello}.json"

    preparar_proxy()
    comprobar_api()
    print("Iniciando Artillery (en Windows puede tardar ~20 s en arrancar)...", flush=True)
    registro: list[str] = []
    hilo = threading.Thread(target=linea_de_tiempo, args=(registro,), daemon=True)

    entorno = {**os.environ, "API_URL": API_URL}
    comando = [str(ARTILLERY), "run", str(AQUI / "artillery.yml"), "--output", str(reporte)]
    proceso = subprocess.Popen(  # noqa: S603 (comando fijo)
        comando,
        env=entorno,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    # El reloj del corte arranca cuando Artillery empieza a enviar carga, no
    # cuando se lanza el proceso: en Windows Artillery tarda ~20 s en arrancar
    # y el corte ocurría antes de la primera solicitud.
    for linea in proceso.stdout:
        print(linea, end="", flush=True)
        if "Phase started" in linea and not hilo.is_alive():
            hilo.start()
    proceso.wait()
    if not registro:
        sys.exit("Artillery nunca inició la fase de carga: el experimento queda INCOMPLETO.")
    hilo.join(timeout=5)
    toxiproxy("POST", "/proxies/postgres", {"enabled": True})  # por si se interrumpió

    (RESULTADOS / f"carga-{sello}-linea.txt").write_text(
        "\n".join(registro) + "\n", encoding="utf-8"
    )
    if not reporte.exists():
        sys.exit("Artillery no generó el reporte: el experimento queda INCOMPLETO.")
    resumen = resumir(reporte, registro)
    (RESULTADOS / f"carga-{sello}-resumen.md").write_text(resumen, encoding="utf-8")
    print("\n" + resumen)


if __name__ == "__main__":
    main()
