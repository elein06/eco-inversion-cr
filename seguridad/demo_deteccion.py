"""Comprueba que Semgrep y Gitleaks detectan un defecto y un secreto controlados.

El defecto y el secreto se crean al ejecutar el script en una carpeta temporal
ignorada por Git y se borran al terminar: un secreto ficticio con commit
quedaría en el historial y haría fallar a Gitleaks para siempre.

    python seguridad/demo_deteccion.py

Termina con código 0 solo si cada herramienta falló con el hallazgo esperado.
"""

import json
import os
import secrets
import shutil
import string
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REPORTES = RAIZ / "reportes" / "seguridad-demo"
ESCANEO = REPORTES / "escaneo"

DEFECTO = '''\
from fastapi import FastAPI

from app.database import get_db_connection

app = FastAPI()


@app.get("/buscar")
def buscar(nombre: str):
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT * FROM cantones WHERE nombre = '{nombre}'")
        return cur.fetchall()
'''


def secreto_ficticio() -> str:
    alfabeto = string.ascii_letters + string.digits
    return "ghp_" + "".join(secrets.choice(alfabeto) for _ in range(36))


def ejecutar(servicio: str) -> int:
    entorno = {
        **os.environ,
        "ESCANEO_DIR": "./reportes/seguridad-demo/escaneo",
        "REPORTES_DIR": "./reportes/seguridad-demo",
    }
    comando = ["docker", "compose", "-f", "docker-compose.seguridad.yml", "run", "--rm", servicio]
    return subprocess.run(comando, cwd=RAIZ, env=entorno, check=False).returncode


def comprobar(nombre: str, codigo: int, detectado: bool) -> bool:
    correcto = codigo == 1 and detectado
    estado = "DETECTADO" if correcto else "NO DETECTADO"
    print(f"{estado}: {nombre} (código de salida {codigo})")
    return correcto


def main() -> int:
    ESCANEO.mkdir(parents=True, exist_ok=True)
    # Los escáneres escriben aquí con el UID 1001 (docker-compose.seguridad.yml).
    REPORTES.chmod(0o777)
    try:
        (ESCANEO / "api_con_defecto.py").write_text(DEFECTO, encoding="utf-8")
        (ESCANEO / "config_con_secreto.txt").write_text(
            f"GITHUB_TOKEN={secreto_ficticio()}\n", encoding="utf-8"
        )

        codigo = ejecutar("semgrep")
        resultados = json.loads((REPORTES / "semgrep.json").read_text(encoding="utf-8"))["results"]
        sql = any("sql" in r["check_id"] for r in resultados)
        semgrep_ok = comprobar("Semgrep, inyección SQL", codigo, sql)

        codigo = ejecutar("gitleaks-archivos")
        fugas = json.loads((REPORTES / "gitleaks-archivos.json").read_text(encoding="utf-8"))
        token = any(f["RuleID"] == "github-pat" for f in fugas)
        gitleaks_ok = comprobar("Gitleaks, token ficticio", codigo, token)
    finally:
        shutil.rmtree(ESCANEO, ignore_errors=True)

    return 0 if semgrep_ok and gitleaks_ok else 1


if __name__ == "__main__":
    sys.exit(main())
