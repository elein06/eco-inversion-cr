"""Políticas de contenedores con Conftest y OPA/Rego (ítem 3.4).

Uso, desde la raíz del repositorio (igual en PowerShell y Bash):

    python politicas/verificar.py                  # pruebas de las reglas + repositorio
    python politicas/verificar.py --demo           # caso permitido y caso rechazado
    python politicas/verificar.py --sin-excepciones  # repositorio ignorando excepciones

Usa el ejecutable "conftest" si está en el PATH (o en la variable CONFTEST);
si no, la imagen oficial de Docker con la misma versión que CI.

Códigos de salida: 0 todo cumple, 1 alguna política rechaza o la demostración
no dio el resultado esperado, 2 Conftest no se pudo ejecutar (comprobación
incompleta, no aprobada).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

VERSION_CONFTEST = "0.71.0"  # misma versión que .github/workflows/politicas.yml
RAIZ = Path(__file__).resolve().parent.parent
POLITICAS = "politicas"
DATOS = "politicas/datos"
EJEMPLOS = "politicas/ejemplos"
REPORTES = RAIZ / "reportes" / "politicas"

# Archivos de construcción, ejecución y despliegue donde aplican las reglas.
PATRON = re.compile(
    r"(^|/)Dockerfile[^/]*$"                 # imágenes propias (U1)
    r"|(^|/)(docker-)?compose[^/]*\.ya?ml$"  # servicios de Compose (P1, U2)
    r"|^\.github/workflows/[^/]+\.ya?ml$"    # workflows de CI/CD (P1)
)


def comando_conftest() -> list[str]:
    ejecutable = os.environ.get("CONFTEST") or shutil.which("conftest")
    if ejecutable:
        return [ejecutable]
    if shutil.which("docker"):
        return [
            "docker", "run", "--rm", "-v", f"{RAIZ}:/project", "-w", "/project",
            f"openpolicyagent/conftest:v{VERSION_CONFTEST}",
        ]
    print("ERROR: no se encontró conftest ni docker. Análisis incompleto.", file=sys.stderr)
    sys.exit(2)


def conftest(*args: str, reporte: str | None = None) -> int:
    cmd = comando_conftest() + list(args)
    print("$ conftest " + " ".join(args), flush=True)
    # Conftest escribe UTF-8; sin encoding explícito Windows lo lee como cp1252.
    resultado = subprocess.run(
        cmd, cwd=RAIZ, capture_output=True, encoding="utf-8", errors="replace"
    )
    salida = resultado.stdout + resultado.stderr
    print(salida, flush=True)
    if reporte:
        REPORTES.mkdir(parents=True, exist_ok=True)
        (REPORTES / reporte).write_text(salida, encoding="utf-8")
    # Conftest sale con 1 cuando una política rechaza; otro código es un error.
    if resultado.returncode not in (0, 1):
        print(f"ERROR: Conftest terminó con {resultado.returncode}. Análisis incompleto.", file=sys.stderr)
        sys.exit(2)
    return resultado.returncode


def archivos_del_repositorio() -> list[str]:
    salida = subprocess.run(
        ["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    archivos = [a for a in salida if PATRON.search(a) and not a.startswith(EJEMPLOS + "/")]
    if not archivos:
        print("ERROR: no se encontraron archivos para analizar. Análisis incompleto.", file=sys.stderr)
        sys.exit(2)
    return archivos


def probar(archivos: list[str], datos: str, reporte: str) -> int:
    return conftest(
        "test", "--no-color", "--combine", "--policy", POLITICAS, "--data", datos,
        *archivos, reporte=reporte,
    )


def demo() -> int:
    """El caso permitido debe pasar y el rechazado fallar con las tres reglas."""
    errores = 0
    permitido = [f"{EJEMPLOS}/permitido/Dockerfile", f"{EJEMPLOS}/permitido/docker-compose.yml"]
    rechazado = [f"{EJEMPLOS}/rechazado/Dockerfile", f"{EJEMPLOS}/rechazado/docker-compose.yml"]

    print("== Caso permitido: se espera código 0 ==")
    if probar(permitido, DATOS, "demo-permitido.txt") != 0:
        print("FALLA: el caso permitido fue rechazado")
        errores += 1

    print("== Caso rechazado: se espera código 1 con P1, U1 y U2 ==")
    codigo = probar(rechazado, DATOS, "demo-rechazado.txt")
    salida = (REPORTES / "demo-rechazado.txt").read_text(encoding="utf-8")
    faltan = [r for r in ("[P1]", "[U1]", "[U2]") if r not in salida]
    if codigo != 1 or faltan:
        print(f"FALLA: el caso rechazado no se rechazó como se esperaba (faltan {faltan})")
        errores += 1

    print("Demostración correcta." if not errores else "Demostración con fallas.")
    return 1 if errores else 0


def main() -> int:
    # La consola de Windows puede no usar UTF-8: evita tildes corruptas.
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="caso permitido y caso rechazado")
    parser.add_argument("--sin-excepciones", action="store_true", help="ignora politicas/datos/excepciones.yaml")
    args = parser.parse_args()

    if args.demo:
        return demo()

    print("== Pruebas de las reglas (conftest verify) ==")
    if conftest("verify", "--no-color", "--policy", POLITICAS, "--data", DATOS, reporte="verify.txt") != 0:
        return 1

    datos = DATOS
    if args.sin_excepciones:
        vacio = REPORTES / "sin-excepciones"
        vacio.mkdir(parents=True, exist_ok=True)
        (vacio / "excepciones.yaml").write_text("excepciones: []\n", encoding="utf-8")
        datos = vacio.relative_to(RAIZ).as_posix()

    archivos = archivos_del_repositorio()
    print("== Políticas sobre el repositorio ==")
    print("Archivos analizados:\n  " + "\n  ".join(archivos))
    return probar(archivos, datos, "repositorio.txt")


if __name__ == "__main__":
    sys.exit(main())
