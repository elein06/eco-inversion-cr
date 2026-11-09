"""
Análisis DAST reproducible con ZAP Automation Framework (ítem 4.7).

Uso, desde la raíz del repositorio:

    python dast/ejecutar_dast.py
        Levanta el ambiente aislado de dast/docker-compose.yml (base desechable
        con datos ficticios + API construida desde backend/), crea la cuenta de
        prueba, ejecuta dast/zap-plan.yaml con la imagen oficial de ZAP y
        destruye todo al terminar.

    python dast/ejecutar_dast.py --objetivo http://127.0.0.1:8000 --zap /ruta/zap.sh \
                                 --base postgresql://usuario:clave@127.0.0.1/base_dast
        Contra una API ya levantada (sin Docker). La API debe apuntar a esa base
        de PRUEBAS, con db/*.sql y dast/datos_ficticios.sql cargados y
        LOGIN_MAX_INTENTOS alto. Requiere psql.

Deja en dast/resultados/<fecha>/ el reporte HTML y JSON de ZAP, las rutas
analizadas, la salida de consola de ZAP, los logs de la API y un resumen.md.

Código de salida: 0 si el análisis se completó sin hallazgos de riesgo Medio o
Alto (los de riesgo Bajo se reportan pero no bloquean); 1 si hay hallazgos que
bloquean o si el análisis no se completó (API caída, sesión inválida, reporte
ausente). Un análisis incompleto nunca se reporta como aprobado.

Solo usa la biblioteca estándar: no hace falta instalar nada además de Docker.
"""

import argparse
import ast
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

DIR_DAST = Path(__file__).resolve().parent
RAIZ = DIR_DAST.parent
COMPOSE = DIR_DAST / "docker-compose.yml"
PROYECTO = "eco-dast"
PUERTO_API = os.environ.get("DAST_PUERTO_API", "18000")

RIESGOS = ["High", "Medium", "Low", "Informational"]
NOMBRE_RIESGO = {"High": "Alto", "Medium": "Medio", "Low": "Bajo", "Informational": "Informativo"}
# riskcode de ZAP -> nombre
RIESGO_POR_CODIGO = {"3": "High", "2": "Medium", "1": "Low", "0": "Informational"}
BLOQUEANTES = {"High", "Medium"}
# Mensaje de ZAP cuando un requestor recibe un código distinto del esperado.
SESION_INVALIDA = "Difference in response code values"
# Rutas que exigen sesión (docs/autenticacion.md); el resto son públicas.
RUTAS_CON_SESION = ("/auth/yo", "/escenarios", "/indice-viabilidad/recalcular")


def log(msg: str) -> None:
    print(f"[dast] {msg}", flush=True)


# ------------------------------------------------------------------ HTTP
def http(metodo: str, url: str, cuerpo: dict | None = None, token: str | None = None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, method=metodo)  # noqa: S310 (URL local del ambiente aislado)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        # La URL es la API del ambiente aislado (127.0.0.1 o la indicada con --objetivo).
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310  # nosemgrep: dynamic-urllib-use-detected
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def esperar_api(base: str, limite_s: int = 120) -> None:
    fin = time.monotonic() + limite_s
    while time.monotonic() < fin:
        try:
            estado, _ = http("GET", f"{base}/health/listo")
            if estado == 200:
                return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        # Espera entre sondeos mientras la API arranca, no una pausa arbitraria.
        time.sleep(2)  # nosemgrep: arbitrary-sleep
    raise RuntimeError(f"La API no respondió en {base}/health/listo en {limite_s} s")


def preparar_cuenta(base: str) -> dict:
    """Cuenta ficticia de rol usuario creada por el flujo real + un escenario propio."""
    email = f"dast-{secrets.token_hex(4)}@prueba.cr"
    password = secrets.token_urlsafe(24)

    estado, cuerpo = http("POST", f"{base}/auth/registro", {"email": email, "password": password})
    if estado != 201:
        raise RuntimeError(f"No se pudo registrar la cuenta de prueba: {estado} {cuerpo}")

    estado, cuerpo = http("POST", f"{base}/auth/login", {"email": email, "password": password})
    if estado != 200:
        raise RuntimeError(f"La cuenta de prueba no pudo iniciar sesión: {estado} {cuerpo}")
    token = cuerpo["access_token"]

    _, indice = http("GET", f"{base}/indice-viabilidad")
    cantones = [f["canton_id"] for f in indice] if isinstance(indice, list) else []
    if not cantones:
        raise RuntimeError("La base no tiene datos ficticios (dast/datos_ficticios.sql)")

    estado, cuerpo = http(
        "POST",
        f"{base}/escenarios",
        {
            "nombre": "Escenario DAST",
            "descripcion": "Datos ficticios para el análisis dinámico",
            "pesos": {"ambiental": 0.4, "inversion": 0.1, "conectividad": 0.3, "seguridad": 0.2},
            "cantones": cantones,
        },
        token,
    )
    if estado != 201:
        raise RuntimeError(f"No se pudo crear el escenario de prueba: {estado} {cuerpo}")

    log(f"Cuenta de prueba {email} (rol usuario) con escenario {cuerpo['escenario_id']}")
    return {
        "DAST_EMAIL": email,
        "DAST_PASSWORD": password,
        "DAST_ESCENARIO_ID": str(cuerpo["escenario_id"]),
    }


# ------------------------------------------------------- Vistas de factores
# Las vistas v_factor_* no están en db/schema.sql: las crea cada ETL. Sin ellas
# /ambiental/factor, /inversion/factor, /infraestructura/factor y
# /seguridad/factor responden 503/500 antes de usar los parámetros, y ZAP no
# llegaría a probar sus consultas. Se toma el SQL directamente de los módulos
# del ETL (sin importarlos ni copiarlo), para que el DAST pruebe las mismas
# vistas que se usan en producción.
VISTAS_ETL = [
    ("etl/sicop/factor_inversion.py", "SQL_FACTOR_INVERSION"),
    ("etl/osm/factor_conectividad.py", "SQL_FACTOR_CONECTIVIDAD"),
    ("etl/snit/factor_ambiental.py", "SQL_FACTOR_AMBIENTAL"),
    ("etl/oij/factor_seguridad.py", "SQL_FACTOR_SEGURIDAD"),
]


def sql_vistas_etl() -> str:
    partes = []
    for ruta, constante in VISTAS_ETL:
        arbol = ast.parse((RAIZ / ruta).read_text(encoding="utf-8"))
        valor = next(
            (
                n.value.value
                for n in arbol.body
                if isinstance(n, ast.Assign)
                and getattr(n.targets[0], "id", None) == constante
                and isinstance(n.value, ast.Constant)
            ),
            None,
        )
        if valor is None:
            raise RuntimeError(f"No se encontró {constante} en {ruta}")
        if constante == "SQL_FACTOR_SEGURIDAD":
            valor = valor.format(filtro_anio="")  # sin datos del OIJ: sin filtro de año
        partes.append(f"-- {ruta} :: {constante}\n{valor.strip()}\n")
    return "\n".join(partes)


def crear_vistas(env: dict, base_local: str | None) -> None:
    sql = sql_vistas_etl()
    if base_local:
        cmd = ["psql", base_local, "-q", "-v", "ON_ERROR_STOP=1"]
    else:
        cmd = [
            "docker",
            "compose",
            "-f",
            str(COMPOSE),
            "-p",
            PROYECTO,
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "eco_dast",
            "-d",
            "eco_inversion_dast",
            "-q",
            "-v",
            "ON_ERROR_STOP=1",
        ]
    # cmd es una lista fija (sin shell); solo la URL de --base la da quien ejecuta el script.
    r = subprocess.run(cmd, input=sql.encode("utf-8"), env=env, capture_output=True)  # noqa: S603  # nosemgrep: dangerous-subprocess-use-audit
    if r.returncode != 0:
        raise RuntimeError(
            "No se pudieron crear las vistas de factores: "
            + r.stderr.decode("utf-8", errors="replace").strip()
        )
    log("Vistas v_factor_* creadas desde el SQL de los ETL")


# ---------------------------------------------------------------- Docker
def compose(*args: str, env: dict, salida=None, check: bool = True) -> int:
    cmd = ["docker", "compose", "-f", str(COMPOSE), "-p", PROYECTO, *args]
    # Lista fija sin shell; args son subcomandos constantes de este archivo.
    r = subprocess.run(cmd, env=env, stdout=salida, stderr=subprocess.STDOUT if salida else None)  # noqa: S603  # nosemgrep: dangerous-subprocess-use-audit
    if check and r.returncode != 0:
        raise RuntimeError(f"Falló: {' '.join(cmd)}")
    return r.returncode


def ejecutar_y_registrar(cmd: list[str], env: dict, archivo: Path) -> int:
    """Ejecuta mostrando la salida en consola y guardándola en un archivo."""
    with archivo.open("w", encoding="utf-8") as f:
        # Lista fija sin shell: docker compose run zap, o zap.sh de --zap.
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)  # noqa: S603  # nosemgrep: dangerous-subprocess-use-audit
        for crudo in proc.stdout:
            linea = crudo.decode("utf-8", errors="replace")
            sys.stdout.write(linea)
            f.write(linea)
            # ZAP registra un código inesperado del job requestor solo como
            # advertencia y sigue: el análisis continuaría SIN sesión y se
            # "aprobaría" sin haber probado las rutas privadas. Se corta aquí.
            if SESION_INVALIDA in linea:
                log("La comprobación de sesión falló: se detiene ZAP")
                proc.terminate()
                proc.wait()
                return 1
        return proc.wait()


# --------------------------------------------------------------- Resumen
def git_commit() -> str:
    try:
        r = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=RAIZ,
            capture_output=True,
            text=True,
            check=True,  # noqa: S607
        )
        sucio = subprocess.run(  # noqa: S603
            ["git", "status", "--porcelain", "--untracked-files=no"],  # noqa: S607
            cwd=RAIZ,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return r.stdout.strip() + (" (con cambios sin commit)" if sucio else "")
    except (OSError, subprocess.CalledProcessError):
        return "desconocido"


JWT = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


def redactar(dir_rep: Path, secretos: list[str]) -> None:
    """
    Los reportes de ZAP citan respuestas reales, entre ellas el access_token de
    /auth/login (alerta 10112). Aunque vienen de un ambiente desechable y
    vencen en 30 min, no se guardan tokens ni la contraseña de prueba en
    artefactos ni en Git (Gitleaks los detecta). Se reemplazan en todos los
    archivos de texto de la corrida.
    """
    for archivo in dir_rep.iterdir():
        if archivo.suffix not in {".json", ".html", ".txt", ".md"}:
            continue
        texto = archivo.read_text(encoding="utf-8", errors="replace")
        nuevo = JWT.sub("[JWT-REDACTADO]", texto)
        for secreto in filter(None, secretos):
            nuevo = nuevo.replace(secreto, "[SECRETO-REDACTADO]")
        if nuevo != texto:
            archivo.write_text(nuevo, encoding="utf-8")


def leer_alertas(reporte: Path) -> list[dict]:
    datos = json.loads(reporte.read_text(encoding="utf-8"))
    alertas = []
    for sitio in datos.get("site", []):
        for a in sitio.get("alerts", []):
            alertas.append(
                {
                    "id": a.get("pluginid"),
                    "nombre": a.get("alert") or a.get("name"),
                    "riesgo": RIESGO_POR_CODIGO.get(str(a.get("riskcode")), "Informational"),
                    "confianza": a.get("confidence"),
                    "cantidad": int(a.get("count") or len(a.get("instances", []))),
                    "ejemplos": sorted({i.get("uri", "") for i in a.get("instances", [])})[:3],
                }
            )
    orden = {r: i for i, r in enumerate(RIESGOS)}
    return sorted(alertas, key=lambda a: (orden[a["riesgo"]], a["nombre"]))


def escribir_resumen(
    dir_rep: Path,
    cod_zap: int,
    veredicto: str,
    motivos: list[str],
    alertas: list[dict],
    rutas: list[str],
    objetivo: str,
    duracion: float,
) -> None:
    conteo = Counter(a["riesgo"] for a in alertas)
    lineas = [
        "# Resumen DAST (ítem 4.7)",
        "",
        f"- **Fecha:** {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- **Commit analizado:** `{git_commit()}`",
        f"- **Objetivo:** `{objetivo}` (ambiente aislado, datos ficticios)",
        "- **Plan:** `dast/zap-plan.yaml` (ZAP 2.16.1, Automation Framework)",
        f"- **Duración:** {duracion / 60:.1f} min",
        f"- **Código de salida de ZAP:** {cod_zap}",
        f"- **Resultado:** **{veredicto}**",
    ]
    lineas += [f"  - {m}" for m in motivos]
    lineas += [
        "",
        "## Alertas por riesgo",
        "",
        "| Riesgo | Tipos de alerta |",
        "|---|---|",
    ]
    lineas += [f"| {NOMBRE_RIESGO[r]} | {conteo.get(r, 0)} |" for r in RIESGOS]
    lineas += [
        "",
        "## Detalle",
        "",
        "| Riesgo | Id | Alerta | Confianza | Instancias | Ejemplo |",
        "|---|---|---|---|---|---|",
    ]
    for a in alertas:
        ejemplo = a["ejemplos"][0] if a["ejemplos"] else ""
        lineas.append(
            f"| {NOMBRE_RIESGO[a['riesgo']]} | {a['id']} | {a['nombre']} | {a['confianza']} "
            f"| {a['cantidad']} | `{ejemplo}` |"
        )
    por_ruta = Counter(urllib.parse.urlsplit(r).path or "/" for r in rutas)
    privadas = sorted(r for r in por_ruta if r.startswith(RUTAS_CON_SESION))
    publicas = sorted(set(por_ruta) - set(privadas))
    lineas += [
        "",
        f"## Rutas analizadas ({len(por_ruta)} rutas, {len(rutas)} URL con parámetros)",
        "",
        "Inventario en `rutas-analizadas.txt` (historial de importación OpenAPI, rastreo y",
        "comprobación de sesión). El análisis activo envía además miles de variantes con",
        "cargas de ataque sobre estas rutas; se ven en `api-log.txt`.",
        "",
        "| Tipo | Ruta | Variantes en el historial |",
        "|---|---|---|",
    ]
    lineas += [f"| con sesión | `{r}` | {por_ruta[r]} |" for r in privadas]
    lineas += [f"| pública | `{r}` | {por_ruta[r]} |" for r in publicas]
    lineas += [
        "",
        "Archivos: `zap-reporte.html`, `zap-reporte.json`, `zap-salida.txt`, `api-log.txt`.",
    ]
    (dir_rep / "resumen.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")


def evaluar(dir_rep: Path, cod_zap: int) -> tuple[str, list[str], list[dict], list[str]]:
    motivos: list[str] = []
    reporte = dir_rep / "zap-reporte.json"
    rutas_txt = dir_rep / "rutas-analizadas.txt"
    salida = (dir_rep / "zap-salida.txt").read_text(encoding="utf-8", errors="replace")

    if SESION_INVALIDA in salida:
        return "INCOMPLETO", ["La comprobación de sesión (requestor) falló"], [], []
    if not reporte.exists():
        return "INCOMPLETO", ["ZAP no generó zap-reporte.json"], [], []
    alertas = leer_alertas(reporte)
    rutas = sorted(set(rutas_txt.read_text(encoding="utf-8").split())) if rutas_txt.exists() else []

    incompleto = False
    duracion_activo = re.search(r"Job activeScan finished, time taken: (\d+):(\d+):(\d+)", salida)
    limite = re.search(r"maxScanDurationInMins:\s*(\d+)", (DIR_DAST / "zap-plan.yaml").read_text())
    if duracion_activo and limite:
        h, m, _ = (int(x) for x in duracion_activo.groups())
        if h * 60 + m >= int(limite.group(1)):
            incompleto = True
            motivos.append(
                f"El análisis activo llegó al límite de {limite.group(1)} min: "
                "quedaron reglas sin ejecutar"
            )
    if not rutas:
        incompleto = True
        motivos.append("No se registraron rutas analizadas")
    if not duracion_activo:
        incompleto = True
        motivos.append("El análisis activo no terminó")

    bloqueantes = [a for a in alertas if a["riesgo"] in BLOQUEANTES]
    if incompleto:
        return "INCOMPLETO", motivos, alertas, rutas
    if cod_zap == 1 or bloqueantes:
        motivos += [f"{NOMBRE_RIESGO[a['riesgo']]}: {a['nombre']}" for a in bloqueantes]
        if cod_zap == 1 and not bloqueantes:
            motivos.append("ZAP terminó con error (ver zap-salida.txt)")
        return "FALLA", motivos, alertas, rutas
    if cod_zap == 2:
        motivos.append("Solo alertas de riesgo Bajo: se reportan, no bloquean")
    return "APROBADO", motivos, alertas, rutas


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--objetivo", help="URL de una API ya levantada (modo sin Docker)")
    ap.add_argument("--zap", help="ruta a zap.sh / zap.bat (modo sin Docker)")
    ap.add_argument("--base", help="URL de la base de PRUEBAS de esa API (modo sin Docker)")
    ap.add_argument("--log-api", help="archivo de log de esa API, para copiarlo a la evidencia")
    ap.add_argument(
        "--demo-sesion-invalida",
        action="store_true",
        help="demostración: entrega a ZAP una contraseña incorrecta; debe terminar INCOMPLETO",
    )
    ap.add_argument("--conservar", action="store_true", help="no destruir el ambiente al terminar")
    args = ap.parse_args()
    sin_docker = bool(args.objetivo)
    if sin_docker and not (args.zap and args.base):
        ap.error("--objetivo requiere --zap y --base")

    dir_rep = DIR_DAST / "resultados" / datetime.now().strftime("%Y%m%d-%H%M%S")
    dir_rep.mkdir(parents=True)
    dir_rep.chmod(0o777)  # el contenedor de ZAP escribe con su propio usuario (uid 1000)

    env = os.environ.copy()
    env["DAST_DIR_REPORTES"] = str(dir_rep)
    env["JWT_SECRET"] = secrets.token_urlsafe(48)  # nuevo en cada corrida, nunca se guarda
    env["DAST_PUERTO_API"] = PUERTO_API

    base = args.objetivo.rstrip("/") if sin_docker else f"http://127.0.0.1:{PUERTO_API}"
    objetivo_zap = base if sin_docker else "http://api:8000"
    inicio = time.monotonic()
    cod_zap = 1
    try:
        if not sin_docker:
            log("Construyendo y levantando el ambiente aislado (db + api)...")
            compose("up", "-d", "--build", "--wait", "db", "api", env=env)
        esperar_api(base)
        crear_vistas(env, args.base if sin_docker else None)
        env.update(preparar_cuenta(base))
        if args.demo_sesion_invalida:
            log("DEMOSTRACIÓN: ZAP recibe una contraseña incorrecta")
            env["DAST_PASSWORD"] = secrets.token_urlsafe(24)

        log("Ejecutando el plan de ZAP (puede tardar ~10-20 min)...")
        if sin_docker:
            env.update({"DAST_TARGET": objetivo_zap, "DAST_REPORTES": str(dir_rep)})
            cmd = [args.zap, "-cmd", "-autorun", str(DIR_DAST / "zap-plan.yaml")]
        else:
            cmd = ["docker", "compose", "-f", str(COMPOSE), "-p", PROYECTO, "run", "--rm", "zap"]
        cod_zap = ejecutar_y_registrar(cmd, env, dir_rep / "zap-salida.txt")
        log(f"ZAP terminó con código {cod_zap}")
    except RuntimeError as exc:
        log(f"ERROR: {exc}")
        (dir_rep / "zap-salida.txt").touch()
    finally:
        if sin_docker and args.log_api:
            shutil.copyfile(args.log_api, dir_rep / "api-log.txt")
        if not sin_docker:
            with (dir_rep / "api-log.txt").open("w", encoding="utf-8") as f:
                compose("logs", "--no-color", "api", env=env, salida=f, check=False)
            if not args.conservar:
                log("Destruyendo el ambiente aislado...")
                compose("down", "-v", "--remove-orphans", env=env, check=False)

    redactar(dir_rep, [env.get("DAST_PASSWORD", ""), env["JWT_SECRET"]])
    veredicto, motivos, alertas, rutas = evaluar(dir_rep, cod_zap)
    escribir_resumen(
        dir_rep,
        cod_zap,
        veredicto,
        motivos,
        alertas,
        rutas,
        objetivo_zap,
        time.monotonic() - inicio,
    )
    ultimo = DIR_DAST / "resultados" / "ultimo-resumen.md"
    shutil.copyfile(dir_rep / "resumen.md", ultimo)

    log(f"Resultado: {veredicto}")
    for m in motivos:
        log(f"  - {m}")
    log(f"Evidencia en {dir_rep.relative_to(RAIZ)}")
    return 0 if veredicto == "APROBADO" else 1


if __name__ == "__main__":
    sys.exit(main())
