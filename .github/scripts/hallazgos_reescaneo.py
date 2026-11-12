"""Convierte los reportes del reescaneo en hallazgos del registro único (ítem 7.6).

El registro único del proyecto son los issues de GitHub. Cada vulnerabilidad
de cada origen (dependencias, imagen del backend, imagen del frontend) es un
hallazgo, identificado por una marca oculta en el cuerpo del issue:

    <!-- reescaneo:<origen>|<ecosistema>|<paquete>|<vulnerabilidad> -->

Qué se registra: una vulnerabilidad nueva se registra si tiene versión
corregida publicada o CVSS de 7.0 o más (UMBRAL_CVSS). Las demás (típicamente
paquetes del sistema operativo de la imagen sin corrección y de severidad
baja) quedan como informativas en el resumen y en el artefacto: no hay nada
que hacer con ellas hasta que se publique una corrección, y en ese momento el
reescaneo las registra.

En cada ejecución:
  - Hallazgo nuevo registrable: se crea un issue con origen, versión afectada (commit y
    digest), evidencia, severidad justificada, responsable, estado y
    tratamiento propuesto.
  - Ya registrado y abierto: se actualiza la sección "Última detección" del
    issue (sin comentarios repetidos cada día).
  - Ya registrado y cerrado: si se cerró como falso positivo o riesgo aceptado
    solo se comenta; si no, se reabre porque la corrección no se sostuvo.
  - Abierto pero ausente en este reescaneo: se comenta una vez y se etiqueta
    "no-detectado". Cerrarlo es una decisión humana: se enlaza el PR correctivo
    y esta ejecución como comprobación (ítem 7.7).

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
# Cierres que no se reabren si la vulnerabilidad sigue apareciendo.
CIERRES_ACEPTADOS = {"falso-positivo", "riesgo-aceptado"}

ORIGENES = {
    "dependencias": "Reescaneo de dependencias (lockfiles del commit desplegado)",
    "imagen-backend": "Reescaneo de la imagen desplegada del backend",
    "imagen-frontend": "Reescaneo de la imagen desplegada del frontend",
}

MARCA = re.compile(r"<!-- reescaneo:(?P<clave>[^>]+?) -->")
ULTIMA = re.compile(r"<!-- ultima-deteccion -->.*?<!-- /ultima-deteccion -->", re.S)


class ErrorRegistro(Exception):
    """Reporte o API inutilizable: el registro queda incompleto."""


@dataclass
class Hallazgo:
    origen: str
    ecosistema: str
    paquete: str
    version: str
    archivo: str
    vuln_id: str
    alias: list[str]
    resumen: str
    cvss: float | None
    corregida_en: list[str] = field(default_factory=list)

    @property
    def clave(self) -> str:
        return f"{self.origen}|{self.ecosistema}|{self.paquete}|{self.vuln_id}"

    @property
    def registrable(self) -> bool:
        return bool(self.corregida_en) or (self.cvss is not None and self.cvss >= UMBRAL_CVSS)

    @property
    def severidad(self) -> str:
        if self.cvss is None:
            return "sin-puntaje"
        if self.cvss >= 9.0:
            return "critica"
        if self.cvss >= 7.0:
            return "alta"
        if self.cvss >= 4.0:
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

    hallazgos: list[Hallazgo] = []
    for resultado in datos.get("results") or []:
        archivo = resultado.get("source", {}).get("path", "")
        for item in resultado.get("packages") or []:
            paquete = item.get("package", {})
            nombre = paquete.get("name", "?")
            vulns = {v["id"]: v for v in item.get("vulnerabilities") or []}
            # Cada grupo reúne los alias de una misma vulnerabilidad
            # (p. ej. GHSA-... y PYSEC-...): un hallazgo por grupo.
            grupos = item.get("groups") or [{"ids": [i]} for i in vulns]
            for grupo in grupos:
                ids = list(grupo.get("ids") or [])
                alias = sorted(set(ids) | set(grupo.get("aliases") or []))
                if not alias:
                    continue
                miembros = [vulns[i] for i in ids if i in vulns]
                resumen = next((v.get("summary") for v in miembros if v.get("summary")), "")
                try:
                    cvss = float(grupo.get("max_severity") or "")
                except ValueError:
                    cvss = None
                hallazgos.append(Hallazgo(
                    origen=origen,
                    ecosistema=paquete.get("ecosystem", "?"),
                    paquete=nombre,
                    version=paquete.get("version", "?"),
                    archivo=archivo,
                    vuln_id=_identificador(alias),
                    alias=alias,
                    resumen=resumen,
                    cvss=cvss,
                    corregida_en=_corregida_en(miembros, nombre),
                ))
    # Un mismo paquete puede aparecer en varias capas o archivos.
    unicos: dict[str, Hallazgo] = {}
    for h in hallazgos:
        unicos.setdefault(h.clave, h)
    return list(unicos.values())


# ---------------------------------------------------------------- textos


def seccion_ultima(h: Hallazgo, contexto: dict) -> str:
    imagen = contexto["imagenes"].get(h.origen)
    imagen = f" · `{imagen}`" if imagen else ""
    return (
        "<!-- ultima-deteccion -->\n"
        f"**Última detección:** {contexto['fecha']} · commit `{contexto['commit']}`"
        f"{imagen}"
        f" · [ejecución]({contexto['ejecucion']})\n"
        "<!-- /ultima-deteccion -->"
    )


def cuerpo_issue(h: Hallazgo, contexto: dict) -> str:
    imagen = contexto["imagenes"].get(h.origen)
    afectada = f"commit desplegado `{contexto['commit']}`"
    if imagen:
        afectada += f"<br>imagen `{imagen}`"
    afectada += f"<br>`{h.paquete}` {h.version}"
    if h.archivo:
        afectada += f" (`{h.archivo}`)"

    if h.cvss is None:
        justificacion = (
            "OSV no publica puntaje CVSS para esta vulnerabilidad. Se asigna al "
            "investigarla según el uso real del paquete."
        )
    else:
        justificacion = (
            f"CVSS máximo {h.cvss:.1f} según OSV (peor caso entre sus alias). "
            "Es la severidad inicial: se ajusta al investigar si la ruta "
            "vulnerable se usa en la aplicación."
        )

    if h.corregida_en:
        tratamiento = (
            f"Corregir: actualizar `{h.paquete}` a {', '.join(h.corregida_en)} o "
            "superior. Si Renovate ya abrió el PR, enlazarlo aquí."
        )
    else:
        tratamiento = (
            "Sin versión corregida publicada. Evaluar mitigación o excepción "
            "temporal con justificación, responsable y fecha de revisión "
            "(docs/seguridad.md, «Qué hacer con un hallazgo»)."
        )

    enlaces = ", ".join(f"[{a}](https://osv.dev/vulnerability/{a})" for a in h.alias)
    filas = [
        ("Origen", ORIGENES.get(h.origen, h.origen)),
        ("Versión afectada", afectada),
        ("Vulnerabilidad", f"{enlaces}<br>{h.resumen}" if h.resumen else enlaces),
        ("Evidencia", f"[Ejecución del reescaneo]({contexto['ejecucion']}), "
                      f"artefacto `reescaneo-{contexto['commit'][:12]}`"),
        ("Severidad", f"**{h.severidad}** — {justificacion}"),
        ("Corrección disponible", ", ".join(h.corregida_en) or "No publicada"),
        ("Responsable", "Por asignar en la revisión de hallazgos (asignar el issue)"),
        ("Estado", "Pendiente de investigación: puede ser un falso positivo"),
        ("Tratamiento propuesto", tratamiento),
    ]
    tabla = "| Campo | Valor |\n|---|---|\n" + "\n".join(
        f"| {k} | {v.replace('|', '/')} |" for k, v in filas
    )
    return (
        f"<!-- reescaneo:{h.clave} -->\n"
        "Hallazgo registrado automáticamente por el reescaneo programado "
        "(ítem 7.6, `docs/actualizaciones.md`).\n\n"
        f"{tabla}\n\n"
        "Al investigarlo: confirmar o descartar, ajustar la severidad y quitar "
        "la etiqueta `pendiente-investigacion`. Un falso positivo o un riesgo "
        "aceptado se cierran con la etiqueta `falso-positivo` o `riesgo-aceptado` "
        "y su justificación en un comentario.\n\n"
        f"{seccion_ultima(h, contexto)}\n"
    )


def titulo_issue(h: Hallazgo) -> str:
    return f"[Reescaneo] {h.vuln_id} en {h.paquete} {h.version} ({h.origen})"


# ---------------------------------------------------------------- GitHub


class GitHub:
    def __init__(self, repo: str, simular: bool):
        self.repo = repo
        self.simular = simular

    def _gh(self, *args: str, entrada: dict | None = None) -> str:
        # Lista de argumentos sin shell; el ejecutable es fijo (gh) y los datos
        # van por stdin en JSON, no en la línea de comandos.
        resultado = subprocess.run(  # noqa: S603  # nosemgrep: dangerous-subprocess-use-audit
            ["gh", *args],  # noqa: S607 - gh viene preinstalado en el runner
            input=json.dumps(entrada) if entrada is not None else None,
            capture_output=True, text=True, encoding="utf-8",
        )
        if resultado.returncode != 0:
            raise ErrorRegistro(f"gh {' '.join(args[:3])}: {resultado.stderr.strip()}")
        return resultado.stdout

    def escribir(self, descripcion: str, *args: str, entrada: dict | None = None) -> None:
        print(("[simulación] " if self.simular else "") + descripcion, flush=True)
        if not self.simular:
            self._gh(*args, entrada=entrada)

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


def sincronizar(hallazgos: list[Hallazgo], origenes: set[str], contexto: dict, gh: GitHub) -> dict:
    existentes: dict[str, dict] = {}
    for issue in gh.issues_reescaneo():
        marca = MARCA.search(issue.get("body") or "")
        if marca:
            existentes[marca.group("clave")] = issue

    gh.asegurar_etiquetas()
    resumen = dict.fromkeys(
        ("nuevos", "actualizados", "reabiertos", "ya_aceptados", "no_detectados",
         "informativos"), 0
    )
    presentes = {h.clave for h in hallazgos}
    api = f"repos/{gh.repo}/issues"

    for h in sorted(hallazgos, key=lambda x: x.clave):
        issue = existentes.get(h.clave)
        if issue is None and not h.registrable:
            print(f"Informativo: {h.vuln_id} en {h.paquete} {h.version} ({h.origen}), "
                  "sin corrección y CVSS bajo el umbral")
            resumen["informativos"] += 1
            continue
        if issue is None:
            etiquetas = ["hallazgo", "reescaneo", "pendiente-investigacion",
                         f"severidad:{h.severidad}"]
            gh.escribir(
                f"Nuevo: {titulo_issue(h)}",
                "api", api, "--method", "POST", "--input", "-",
                entrada={"title": titulo_issue(h), "body": cuerpo_issue(h, contexto),
                         "labels": etiquetas},
            )
            resumen["nuevos"] += 1
            continue

        numero = issue["number"]
        etiquetas = {e["name"] for e in issue.get("labels", [])}
        # lambda: el texto nuevo no se interpreta como plantilla de re.sub.
        nueva = seccion_ultima(h, contexto)
        cuerpo = ULTIMA.sub(lambda _, texto=nueva: texto, issue.get("body") or "")
        cambios: dict = {"body": cuerpo}
        ejecucion = f"([ejecución]({contexto['ejecucion']}))"
        if issue["state"] == "closed":
            aceptado = ", ".join(sorted(etiquetas & CIERRES_ACEPTADOS))
            if aceptado:
                gh.escribir(
                    f"#{numero}: sigue presente, cerrado como {aceptado}",
                    "api", f"{api}/{numero}/comments", "--method", "POST", "--input", "-",
                    entrada={"body": (
                        f"Sigue presente en el reescaneo del {contexto['fecha']} {ejecucion}. "
                        "Se mantiene cerrado por la decisión registrada; revisar si la "
                        "fecha de revisión ya venció."
                    )},
                )
                resumen["ya_aceptados"] += 1
                continue
            cambios["state"] = "open"
            gh.escribir(
                f"#{numero}: reaparece, se reabre",
                "api", f"{api}/{numero}/comments", "--method", "POST", "--input", "-",
                entrada={"body": (
                    f"Reapareció en el reescaneo del {contexto['fecha']} sobre el commit "
                    f"`{contexto['commit']}` {ejecucion}. La corrección no se sostuvo: "
                    "se reabre."
                )},
            )
            resumen["reabiertos"] += 1
        else:
            resumen["actualizados"] += 1
        if "no-detectado" in etiquetas:
            gh.escribir(f"#{numero}: quitar no-detectado",
                        "api", f"{api}/{numero}/labels/no-detectado", "--method", "DELETE")
        gh.escribir(f"#{numero}: actualizar última detección",
                    "api", f"{api}/{numero}", "--method", "PATCH", "--input", "-", entrada=cambios)

    # Abiertos que este reescaneo ya no ve (solo de los orígenes analizados).
    for clave, issue in sorted(existentes.items()):
        origen = clave.split("|", 1)[0]
        etiquetas = {e["name"] for e in issue.get("labels", [])}
        if (issue["state"] != "open" or clave in presentes or origen not in origenes
                or "no-detectado" in etiquetas):
            continue
        numero = issue["number"]
        gh.escribir(
            f"#{numero}: ya no se detecta",
            "api", f"{api}/{numero}/comments", "--method", "POST", "--input", "-",
            entrada={"body": (
                f"El reescaneo del {contexto['fecha']} sobre el commit `{contexto['commit']}` "
                f"ya no lo detecta ([ejecución]({contexto['ejecucion']})). Para cerrarlo: "
                "enlazar el PR correctivo y esta ejecución como comprobación (ítem 7.7)."
            )},
        )
        gh.escribir(f"#{numero}: etiqueta no-detectado",
                    "api", f"{api}/{numero}/labels", "--method", "POST", "--input", "-",
                    entrada={"labels": ["no-detectado"]})
        resumen["no_detectados"] += 1
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
        print(f"{len(hallazgos)} vulnerabilidades en {', '.join(sorted(reportes))}")
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
            salida.write(f"- Vulnerabilidades encontradas: {len(hallazgos)}\n- {texto}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
