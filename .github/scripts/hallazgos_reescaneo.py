"""Convierte los reportes del reescaneo en hallazgos del registro único (ítem 7.6).

El registro único del proyecto son los issues de GitHub. Un hallazgo es un
paquete vulnerable de un origen (dependencias, imagen del backend, imagen del
frontend), con todas sus vulnerabilidades en una tabla. Se identifica por una
marca oculta en el cuerpo del issue:

    <!-- reescaneo-paquete:<origen>|<ecosistema>|<paquete> -->

Se agrupa por paquete porque así se corrige: actualizar curl corrige sus 24
CVE a la vez. Un issue por CVE produjo 80 issues en la primera corrida, sin
nada distinto que hacer en cada uno.

Qué se registra: un paquete se registra si alguna de sus vulnerabilidades
tiene versión corregida publicada o CVSS de 7.0 o más (UMBRAL_CVSS). Los demás
quedan como informativos en el resumen y en el artefacto.

En cada ejecución:
  - Paquete nuevo registrable: se crea un issue con origen, versión afectada
    (commit y digest), evidencia, severidad justificada, responsable, estado,
    tratamiento y la tabla de vulnerabilidades.
  - Ya registrado y abierto: se actualiza la descripción (tabla, versión,
    última detección) y la etiqueta de severidad. Solo se comenta si cambió el
    conjunto de vulnerabilidades.
  - Ya registrado y cerrado: si se cerró como falso positivo o riesgo aceptado
    solo se comenta cuando aparecen vulnerabilidades nuevas; si no, se reabre
    porque la corrección no se sostuvo.
  - Abierto pero ausente en este reescaneo: se comenta una vez y se etiqueta
    "no-detectado". Cerrarlo es una decisión humana: se enlaza el PR correctivo
    y esta ejecución como comprobación (ítem 7.7).
  - Issues del formato anterior (uno por CVE, marca "reescaneo:"): se cierran
    como "not planned" con un enlace al issue agrupado que los reemplaza.

Las escrituras van espaciadas (PAUSA_S) porque GitHub limita la creación
rápida de contenido; si aun así responde con ese límite, se espera y se
reintenta.

Uso (en el workflow .github/workflows/reescaneo.yml):

    python .github/scripts/hallazgos_reescaneo.py \
        --reporte dependencias=reportes/osv-dependencias.json \
        --reporte imagen-backend=reportes/osv-imagen-backend.json \
        --version-desplegada <commit> \
        --imagen imagen-backend=docker.io/u/eco-inversion-backend@sha256:... \
        --ejecucion <URL de la ejecución> [--simular]

--simular no escribe en GitHub: imprime lo que haría (se usa en los PR).
Requiere el CLI gh con GH_TOKEN y GITHUB_REPOSITORY, salvo en --simular sin
token. Códigos de salida: 0 registro al día, 2 reporte ilegible o error de la
API de GitHub (registro incompleto, no aprobado).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ETIQUETAS = {
    "hallazgo": ("5319e7", "Hallazgo del registro único"),
    "reescaneo": ("0e8a16", "Detectado por el reescaneo programado (7.6)"),
    "pendiente-investigacion": ("fbca04", "Sin confirmar: falta investigar"),
    "no-detectado": ("c2e0c6", "El último reescaneo ya no lo detecta"),
    "severidad:critica": ("b60205", "CVSS 9.0 o más"),
    "severidad:alta": ("d93f0b", "CVSS 7.0 a 8.9"),
    "severidad:media": ("fbca04", "CVSS 4.0 a 6.9"),
    "severidad:baja": ("0e8a16", "CVSS menor que 4.0"),
    "severidad:sin-puntaje": ("bfdadc", "OSV no publica puntaje CVSS"),
}
# Severidad a partir de la cual se registra aunque no haya corrección publicada.
UMBRAL_CVSS = 7.0
# Cierres que no se reabren si el paquete sigue apareciendo.
CIERRES_ACEPTADOS = {"falso-positivo", "riesgo-aceptado"}
# Segundos entre escrituras, y espera ante el límite de GitHub.
PAUSA_S = 1.0
ESPERA_LIMITE_S = 60
REINTENTOS = 3

ORIGENES = {
    "dependencias": "Reescaneo de dependencias (lockfiles del commit desplegado)",
    "imagen-backend": "Reescaneo de la imagen desplegada del backend",
    "imagen-frontend": "Reescaneo de la imagen desplegada del frontend",
}

MARCA = re.compile(r"<!-- reescaneo-paquete:(?P<clave>[^>]+?) -->")
MARCA_ANTERIOR = re.compile(r"<!-- reescaneo:(?P<clave>[^>]+?) -->")
MARCA_VULNS = re.compile(r"<!-- vulns:(?P<ids>[^>]*?) -->")


class ErrorRegistro(Exception):
    """Reporte o API inutilizable: el registro queda incompleto."""


@dataclass
class Vulnerabilidad:
    vuln_id: str
    alias: list[str]
    resumen: str
    cvss: float | None
    corregida_en: list[str] = field(default_factory=list)


@dataclass
class Hallazgo:
    """Un paquete vulnerable de un origen, con todas sus vulnerabilidades."""

    origen: str
    ecosistema: str
    paquete: str
    version: str
    archivo: str
    vulns: list[Vulnerabilidad] = field(default_factory=list)

    @property
    def clave(self) -> str:
        return f"{self.origen}|{self.ecosistema}|{self.paquete}"

    @property
    def ids(self) -> list[str]:
        return sorted(v.vuln_id for v in self.vulns)

    @property
    def cvss(self) -> float | None:
        puntajes = [v.cvss for v in self.vulns if v.cvss is not None]
        return max(puntajes) if puntajes else None

    @property
    def corregida_en(self) -> list[str]:
        return sorted({c for v in self.vulns for c in v.corregida_en})

    @property
    def registrable(self) -> bool:
        return bool(self.corregida_en) or (self.cvss is not None and self.cvss >= UMBRAL_CVSS)

    @property
    def severidad(self) -> str:
        cvss = self.cvss
        if cvss is None:
            return "sin-puntaje"
        if cvss >= 9.0:
            return "critica"
        if cvss >= 7.0:
            return "alta"
        if cvss >= 4.0:
            return "media"
        return "baja"


# ---------------------------------------------------------------- reportes


def _identificador(ids: list[str]) -> str:
    """Id estable para un grupo de alias: CVE si existe, si no el menor."""
    cves = sorted(i for i in ids if i.startswith("CVE-"))
    return cves[0] if cves else sorted(ids)[0]


def _corregida_en(vulns: list[dict], paquete: str) -> list[str]:
    versiones: set[str] = set()
    for vuln in vulns:
        for afectado in vuln.get("affected", []):
            if afectado.get("package", {}).get("name", "").lower() != paquete.lower():
                continue
            for rango in afectado.get("ranges", []):
                for evento in rango.get("events", []):
                    if "fixed" in evento:
                        versiones.add(evento["fixed"])
    return sorted(versiones)


def leer_reporte(origen: str, ruta: Path) -> list[Hallazgo]:
    """Lee un reporte JSON de OSV-Scanner v2 (scan source o scan image)."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ErrorRegistro(f"no se pudo leer {ruta}: {error}") from error
    if not isinstance(datos, dict) or "results" not in datos:
        raise ErrorRegistro(f"{ruta} no tiene el formato de OSV-Scanner (falta 'results')")

    paquetes: dict[str, Hallazgo] = {}
    for resultado in datos.get("results") or []:
        archivo = resultado.get("source", {}).get("path", "")
        for item in resultado.get("packages") or []:
            paquete = item.get("package", {})
            nombre = paquete.get("name", "?")
            h = Hallazgo(
                origen=origen,
                ecosistema=paquete.get("ecosystem", "?"),
                paquete=nombre,
                version=paquete.get("version", "?"),
                archivo=archivo,
            )
            # Un mismo paquete puede aparecer en varias capas o archivos.
            h = paquetes.setdefault(h.clave, h)
            conocidas = {v.vuln_id for v in h.vulns}
            vulns = {v["id"]: v for v in item.get("vulnerabilities") or []}
            # Cada grupo reúne los alias de una misma vulnerabilidad
            # (p. ej. GHSA-... y PYSEC-...): una fila por grupo.
            grupos = item.get("groups") or [{"ids": [i]} for i in vulns]
            for grupo in grupos:
                ids = list(grupo.get("ids") or [])
                alias = sorted(set(ids) | set(grupo.get("aliases") or []))
                if not alias or _identificador(alias) in conocidas:
                    continue
                miembros = [vulns[i] for i in ids if i in vulns]
                try:
                    cvss = float(grupo.get("max_severity") or "")
                except ValueError:
                    cvss = None
                h.vulns.append(Vulnerabilidad(
                    vuln_id=_identificador(alias),
                    alias=alias,
                    resumen=next((v.get("summary") for v in miembros if v.get("summary")), ""),
                    cvss=cvss,
                    corregida_en=_corregida_en(miembros, nombre),
                ))
                conocidas.add(_identificador(alias))
    return [h for h in paquetes.values() if h.vulns]


# ---------------------------------------------------------------- textos


def _celda(texto: str) -> str:
    return texto.replace("|", "/").replace("\n", " ")


def tratamiento(h: Hallazgo) -> str:
    if h.origen.startswith("imagen-") and not h.ecosistema.startswith(("PyPI", "npm")):
        return (
            "Paquete del sistema de la imagen base: se corrige actualizando la imagen "
            "(PR de Renovate que cambia su digest, o reconstruir sobre la misma etiqueta) "
            "y reescaneando. Las versiones corregidas que publica OSV pueden ser de otra "
            "versión de la distribución (p. ej. Debian inestable) y no estar disponibles "
            "todavía para la imagen base: en ese caso se mantiene abierto hasta que la "
            "distribución publique la actualización, o se acepta el riesgo con "
            "justificación, responsable y fecha de revisión."
        )
    if h.corregida_en:
        return (
            f"Actualizar `{h.paquete}` a una versión corregida ({', '.join(h.corregida_en)}). "
            "Si Renovate ya abrió el PR, enlazarlo aquí."
        )
    return (
        "Sin versión corregida publicada. Evaluar mitigación o excepción temporal con "
        "justificación, responsable y fecha de revisión (docs/seguridad.md, "
        "«Qué hacer con un hallazgo»)."
    )


def cuerpo_issue(h: Hallazgo, contexto: dict) -> str:
    imagen = contexto["imagenes"].get(h.origen)
    afectada = f"commit desplegado `{contexto['commit']}`"
    if imagen:
        afectada += f"<br>imagen `{imagen}`"
    afectada += f"<br>`{h.paquete}` {h.version} ({h.ecosistema})"
    if h.archivo:
        afectada += f", `{h.archivo}`"

    if h.cvss is None:
        justificacion = "OSV no publica puntaje CVSS; se asigna al investigar."
    else:
        justificacion = (
            f"CVSS máximo {h.cvss:.1f} entre sus {len(h.vulns)} vulnerabilidades, según OSV. "
            "Es la severidad inicial: se ajusta al investigar si la ruta vulnerable se usa."
        )
    filas = [
        ("Origen", ORIGENES.get(h.origen, h.origen)),
        ("Versión afectada", afectada),
        ("Evidencia", f"[Ejecución del reescaneo]({contexto['ejecucion']}), "
                      f"artefacto `reescaneo-{contexto['commit'][:12]}`"),
        ("Severidad", f"**{h.severidad}** — {justificacion}"),
        ("Responsable", "Por asignar en la revisión de hallazgos (asignar el issue)"),
        ("Estado", "Pendiente de investigación: puede incluir falsos positivos"),
        ("Tratamiento propuesto", tratamiento(h)),
        ("Última detección", f"{contexto['fecha']} · [ejecución]({contexto['ejecucion']})"),
    ]
    tabla = "| Campo | Valor |\n|---|---|\n" + "\n".join(
        f"| {k} | {_celda(v)} |" for k, v in filas
    )
    vulns = "| Vulnerabilidad | CVSS | Corregida en | Resumen |\n|---|---|---|---|\n" + "\n".join(
        "| {} | {} | {} | {} |".format(
            ", ".join(f"[{a}](https://osv.dev/vulnerability/{a})" for a in v.alias),
            f"{v.cvss:.1f}" if v.cvss is not None else "—",
            _celda(", ".join(v.corregida_en) or "No publicada"),
            _celda(v.resumen[:140]),
        )
        for v in sorted(h.vulns, key=lambda v: (-(v.cvss or 0), v.vuln_id))
    )
    return (
        f"<!-- reescaneo-paquete:{h.clave} -->\n"
        f"<!-- vulns:{','.join(h.ids)} -->\n"
        "Hallazgo registrado por el reescaneo programado (ítem 7.6, "
        "`docs/actualizaciones.md`). El reescaneo mantiene esta descripción al día; "
        "las decisiones van en comentarios.\n\n"
        f"{tabla}\n\n"
        f"### Vulnerabilidades ({len(h.vulns)})\n\n{vulns}\n\n"
        "Al investigarlo: confirmar o descartar, ajustar la severidad y quitar la "
        "etiqueta `pendiente-investigacion`. Un falso positivo o un riesgo aceptado se "
        "cierran con la etiqueta `falso-positivo` o `riesgo-aceptado` y su "
        "justificación en un comentario.\n"
    )


def titulo_issue(h: Hallazgo) -> str:
    cantidad = f"{len(h.vulns)} vulnerabilidad" + ("es" if len(h.vulns) != 1 else "")
    return f"[Reescaneo] {h.paquete} {h.version}: {cantidad} ({h.origen})"


# ---------------------------------------------------------------- GitHub


class GitHub:
    def __init__(self, repo: str, simular: bool, pausa: float = PAUSA_S):
        self.repo = repo
        self.simular = simular
        self.pausa = pausa

    def _gh(self, *args: str, entrada: dict | None = None) -> str:
        # Lista de argumentos sin shell; el ejecutable es fijo (gh) y los datos
        # van por stdin en JSON, no en la línea de comandos.
        for intento in range(REINTENTOS + 1):
            resultado = subprocess.run(  # noqa: S603  # nosemgrep: dangerous-subprocess-use-audit
                ["gh", *args],  # noqa: S607 - gh viene preinstalado en el runner
                input=json.dumps(entrada) if entrada is not None else None,
                capture_output=True, text=True, encoding="utf-8",
            )
            if resultado.returncode == 0:
                return resultado.stdout
            error = resultado.stderr.strip()
            limite = "rate limit" in error.lower() or "HTTP 429" in error
            if not limite or intento == REINTENTOS:
                break
            print(f"Límite de GitHub; se reintenta en {ESPERA_LIMITE_S} s", flush=True)
            time.sleep(ESPERA_LIMITE_S)
        raise ErrorRegistro(f"gh {' '.join(args[:3])}: {error}")

    def escribir(self, descripcion: str, *args: str, entrada: dict | None = None) -> dict:
        print(("[simulación] " if self.simular else "") + descripcion, flush=True)
        if self.simular:
            return {"number": 0}
        salida = self._gh(*args, entrada=entrada)
        time.sleep(self.pausa)
        try:
            return json.loads(salida) if salida.strip() else {}
        except ValueError:
            return {}

    def issues_reescaneo(self) -> list[dict]:
        if self.simular and not os.environ.get("GH_TOKEN"):
            print("[simulación] Sin GH_TOKEN: se asume un registro vacío.")
            return []
        try:
            salida = self._gh(
                "api", "--paginate", "--slurp",
                f"repos/{self.repo}/issues?state=all&labels=reescaneo&per_page=100",
            )
        except ErrorRegistro as error:
            if not self.simular:
                raise
            print(f"[simulación] No se pudo leer el registro ({error}): se asume vacío.")
            return []
        paginas = json.loads(salida)
        return [i for pagina in paginas for i in pagina if "pull_request" not in i]

    def asegurar_etiquetas(self) -> None:
        for nombre, (color, descripcion) in ETIQUETAS.items():
            self.escribir(
                f"Etiqueta {nombre}",
                "label", "create", nombre, "--repo", self.repo,
                "--color", color, "--description", descripcion, "--force",
            )


# ---------------------------------------------------------------- registro


def _etiquetas(issue: dict) -> set[str]:
    return {e["name"] for e in issue.get("labels", [])}


def _ids_registrados(issue: dict) -> set[str]:
    marca = MARCA_VULNS.search(issue.get("body") or "")
    return set(filter(None, marca.group("ids").split(","))) if marca else set()


def _cambios(antes: set[str], ahora: set[str]) -> str:
    partes = []
    if ahora - antes:
        partes.append("nuevas: " + ", ".join(sorted(ahora - antes)))
    if antes - ahora:
        partes.append("ya no aparecen: " + ", ".join(sorted(antes - ahora)))
    return "; ".join(partes)


def sincronizar(hallazgos: list[Hallazgo], origenes: set[str], contexto: dict, gh: GitHub) -> dict:
    existentes: dict[str, dict] = {}
    anteriores: list[tuple[str, dict]] = []
    for issue in gh.issues_reescaneo():
        cuerpo = issue.get("body") or ""
        if marca := MARCA.search(cuerpo):
            existentes[marca.group("clave")] = issue
        elif marca := MARCA_ANTERIOR.search(cuerpo):
            anteriores.append((marca.group("clave"), issue))

    gh.asegurar_etiquetas()
    resumen = dict.fromkeys(
        ("nuevos", "actualizados", "reabiertos", "ya_aceptados", "no_detectados",
         "informativos", "reemplazados"), 0
    )
    presentes = {h.clave for h in hallazgos}
    numeros: dict[str, int] = {}
    api = f"repos/{gh.repo}/issues"
    ejecucion = f"([ejecución]({contexto['ejecucion']}))"

    for h in sorted(hallazgos, key=lambda x: x.clave):
        issue = existentes.get(h.clave)
        if issue is None and not h.registrable:
            print(f"Informativo: {h.paquete} {h.version} ({h.origen}), {len(h.vulns)} "
                  "vulnerabilidades sin corrección y con CVSS bajo el umbral")
            resumen["informativos"] += 1
            continue
        if issue is None:
            creado = gh.escribir(
                f"Nuevo: {titulo_issue(h)}",
                "api", api, "--method", "POST", "--input", "-",
                entrada={"title": titulo_issue(h), "body": cuerpo_issue(h, contexto),
                         "labels": ["hallazgo", "reescaneo", "pendiente-investigacion",
                                    f"severidad:{h.severidad}"]},
            )
            numeros[h.clave] = creado.get("number", 0)
            resumen["nuevos"] += 1
            continue

        numero = issue["number"]
        numeros[h.clave] = numero
        etiquetas = _etiquetas(issue)
        cambios = _cambios(_ids_registrados(issue), set(h.ids))
        nuevas = {e for e in etiquetas if not e.startswith("severidad:")} - {"no-detectado"}
        nuevas.add(f"severidad:{h.severidad}")
        parche: dict = {"title": titulo_issue(h), "body": cuerpo_issue(h, contexto),
                        "labels": sorted(nuevas)}
        comentario = None
        if issue["state"] == "closed":
            aceptado = ", ".join(sorted(etiquetas & CIERRES_ACEPTADOS))
            if aceptado:
                resumen["ya_aceptados"] += 1
                # Respeta la decisión: solo avisa si aparecieron vulnerabilidades nuevas.
                if set(h.ids) - _ids_registrados(issue):
                    gh.escribir(
                        f"#{numero}: cerrado como {aceptado}, con vulnerabilidades nuevas",
                        "api", f"{api}/{numero}/comments", "--method", "POST", "--input", "-",
                        entrada={"body": (
                            f"El reescaneo del {contexto['fecha']} {ejecucion} encontró "
                            f"vulnerabilidades nuevas en este paquete ({cambios}). Se mantiene "
                            f"cerrado como {aceptado}; revisar si la decisión sigue vigente."
                        )},
                    )
                continue
            parche["state"] = "open"
            comentario = (
                f"Reapareció en el reescaneo del {contexto['fecha']} sobre el commit "
                f"`{contexto['commit']}` {ejecucion}. La corrección no se sostuvo: se reabre."
            )
            resumen["reabiertos"] += 1
        else:
            resumen["actualizados"] += 1
            if cambios:
                comentario = (
                    f"Cambió el conjunto de vulnerabilidades en el reescaneo del "
                    f"{contexto['fecha']} {ejecucion}: {cambios}."
                )
        if comentario:
            gh.escribir(f"#{numero}: comentario",
                        "api", f"{api}/{numero}/comments", "--method", "POST", "--input", "-",
                        entrada={"body": comentario})
        gh.escribir(f"#{numero}: actualizar ({cambios or 'sin cambios'})",
                    "api", f"{api}/{numero}", "--method", "PATCH", "--input", "-",
                    entrada=parche)

    # Abiertos que este reescaneo ya no ve (solo de los orígenes analizados).
    for clave, issue in sorted(existentes.items()):
        origen = clave.split("|", 1)[0]
        if (issue["state"] != "open" or clave in presentes or origen not in origenes
                or "no-detectado" in _etiquetas(issue)):
            continue
        numero = issue["number"]
        gh.escribir(
            f"#{numero}: ya no se detecta",
            "api", f"{api}/{numero}/comments", "--method", "POST", "--input", "-",
            entrada={"body": (
                f"El reescaneo del {contexto['fecha']} sobre el commit `{contexto['commit']}` "
                f"ya no lo detecta {ejecucion}. Para cerrarlo: enlazar el PR correctivo y "
                "esta ejecución como comprobación (ítem 7.7)."
            )},
        )
        gh.escribir(f"#{numero}: etiqueta no-detectado",
                    "api", f"{api}/{numero}/labels", "--method", "POST", "--input", "-",
                    entrada={"labels": ["no-detectado"]})
        resumen["no_detectados"] += 1

    # Formato anterior (un issue por CVE): se cierran apuntando al agrupado.
    for clave, issue in anteriores:
        if issue["state"] != "open":
            continue
        numero = issue["number"]
        nuevo = numeros.get(clave.rsplit("|", 1)[0])
        destino = (f"el issue agrupado #{nuevo}" if nuevo else
                   "el registro agrupado por paquete (este paquete no cumple hoy el "
                   "criterio de registro o ya no se detecta)")
        gh.escribir(
            f"#{numero}: reemplazado por {'#' + str(nuevo) if nuevo else 'registro agrupado'}",
            "api", f"{api}/{numero}/comments", "--method", "POST", "--input", "-",
            entrada={"body": (
                "El registro del reescaneo pasó a un issue por paquete en lugar de uno por "
                f"vulnerabilidad. Esta vulnerabilidad sigue en {destino}."
            )},
        )
        gh.escribir(f"#{numero}: cerrar como not planned",
                    "api", f"{api}/{numero}", "--method", "PATCH", "--input", "-",
                    entrada={"state": "closed", "state_reason": "not_planned"})
        resumen["reemplazados"] += 1
    return resumen


def pares(valores: list[str], opcion: str) -> dict[str, str]:
    resultado = {}
    for valor in valores:
        clave, sep, dato = valor.partition("=")
        if not sep or clave not in ORIGENES or not dato:
            raise SystemExit(
                f"{opcion} {valor!r}: se espera origen=valor con origen en {sorted(ORIGENES)}"
            )
        resultado[clave] = dato
    return resultado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--reporte", action="append", default=[], required=True)
    parser.add_argument("--imagen", action="append", default=[])
    parser.add_argument("--version-desplegada", required=True)
    parser.add_argument("--ejecucion", required=True)
    parser.add_argument("--simular", action="store_true")
    args = parser.parse_args(argv)

    reportes = pares(args.reporte, "--reporte")
    contexto = {
        "commit": args.version_desplegada,
        "imagenes": pares(args.imagen, "--imagen"),
        "ejecucion": args.ejecucion,
        "fecha": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
    }
    try:
        hallazgos = [
            h for origen, ruta in reportes.items() for h in leer_reporte(origen, Path(ruta))
        ]
        total = sum(len(h.vulns) for h in hallazgos)
        print(f"{total} vulnerabilidades en {len(hallazgos)} paquetes "
              f"({', '.join(sorted(reportes))})")
        gh = GitHub(os.environ.get("GITHUB_REPOSITORY", "local/simulacion"), args.simular)
        resumen = sincronizar(hallazgos, set(reportes), contexto, gh)
    except ErrorRegistro as error:
        print(f"ERROR: {error}. Registro incompleto.", file=sys.stderr)
        return 2

    texto = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in resumen.items())
    print(f"Registro de hallazgos al día ({texto})")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as salida:
            modo = " (simulación)" if args.simular else ""
            salida.write(f"## Registro de hallazgos{modo}\n\n")
            salida.write(f"- Commit desplegado: `{contexto['commit']}`\n")
            for origen, imagen in sorted(contexto["imagenes"].items()):
                salida.write(f"- {origen}: `{imagen}`\n")
            salida.write(f"- {total} vulnerabilidades en {len(hallazgos)} paquetes\n")
            salida.write("\n| Origen | Paquete | Versión | Vulnerabilidades | Severidad |\n"
                         "|---|---|---|---|---|\n")
            for h in sorted(hallazgos, key=lambda x: x.clave):
                salida.write(f"| {h.origen} | {h.paquete} | {h.version} | {len(h.vulns)} | "
                             f"{h.severidad}{'' if h.registrable else ' (informativo)'} |\n")
            salida.write(f"\n{texto}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
