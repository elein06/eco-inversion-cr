"""Autoprueba del registro de hallazgos del reescaneo (ítem 7.6).

Comprueba, sin red ni GitHub, que un reporte de OSV-Scanner produce un
hallazgo por paquete vulnerable y que el registro crea, actualiza, reabre,
marca como no detectados y reemplaza (formato anterior) los issues correctos.
El workflow la ejecuta antes de registrar.

    python .github/scripts/test_hallazgos_reescaneo.py -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hallazgos_reescaneo as hr  # noqa: E402


def _afectado(nombre: str, corregida: str | None) -> list[dict]:
    eventos = [{"introduced": "0"}] + ([{"fixed": corregida}] if corregida else [])
    return [{"package": {"name": nombre}, "ranges": [{"type": "ECOSYSTEM", "events": eventos}]}]


# Forma de un reporte JSON de OSV-Scanner v2. starlette: dos vulnerabilidades,
# una con dos alias (GHSA + PYSEC). zlib: sin corrección ni puntaje. curl
# aparece en dos capas de la imagen: debe contar una sola vez.
REPORTE = {
    "results": [{
        "source": {"path": "/src/backend/requirements.lock", "type": "lockfile"},
        "packages": [
            {
                "package": {"name": "starlette", "version": "0.40.0", "ecosystem": "PyPI"},
                "vulnerabilities": [
                    {"id": "GHSA-aaaa-bbbb-cccc", "summary": "DoS en multipart",
                     "affected": _afectado("starlette", "0.40.1")},
                    {"id": "PYSEC-2099-1", "affected": []},
                    {"id": "GHSA-dddd-eeee-ffff", "summary": "Lectura de archivos",
                     "affected": _afectado("starlette", "0.41.0")},
                ],
                "groups": [
                    {"ids": ["GHSA-aaaa-bbbb-cccc", "PYSEC-2099-1"],
                     "aliases": ["CVE-2099-0001"], "max_severity": "7.5"},
                    {"ids": ["GHSA-dddd-eeee-ffff"], "max_severity": "5.3"},
                ],
            },
            {
                "package": {"name": "zlib", "version": "1.2.13", "ecosystem": "Debian:12"},
                "vulnerabilities": [{"id": "DEBIAN-CVE-2099-0002", "affected": []}],
                "groups": [{"ids": ["DEBIAN-CVE-2099-0002"], "max_severity": ""}],
            },
            {
                "package": {"name": "curl", "version": "8.22.0-r0", "ecosystem": "Alpine:v3.22"},
                "vulnerabilities": [{"id": "ALPINE-CVE-2099-0003",
                                     "affected": _afectado("curl", "8.23.0-r0")}],
                "groups": [{"ids": ["ALPINE-CVE-2099-0003"], "aliases": ["CVE-2099-0003"],
                            "max_severity": "9.1"}],
            },
        ],
    }, {
        "source": {"path": "/lib/apk/db/installed", "type": "os"},
        "packages": [{
            "package": {"name": "curl", "version": "8.22.0-r0", "ecosystem": "Alpine:v3.22"},
            "vulnerabilities": [{"id": "ALPINE-CVE-2099-0003", "affected": []}],
            "groups": [{"ids": ["ALPINE-CVE-2099-0003"], "aliases": ["CVE-2099-0003"],
                        "max_severity": "9.1"}],
        }],
    }]
}

CONTEXTO = {"commit": "abc123", "imagenes": {}, "ejecucion": "https://ejemplo/run/1",
            "fecha": "2026-11-12 12:00 UTC"}
STARLETTE = "dependencias|PyPI|starlette"
ZLIB = "dependencias|Debian:12|zlib"


class GitHubFalso(hr.GitHub):
    def __init__(self, issues):
        super().__init__("org/repo", simular=False, pausa=0)
        self.issues = issues
        self.llamadas: list[tuple] = []
        self.siguiente = 200

    def issues_reescaneo(self):
        return self.issues

    def _gh(self, *args, entrada=None):
        self.llamadas.append((args, entrada))
        if args[1] == "repos/org/repo/issues" and "POST" in args:
            self.siguiente += 1
            return json.dumps({"number": self.siguiente})
        return ""

    def acciones(self, ruta_final: str, metodo: str):
        return [e for a, e in self.llamadas if a[1].endswith(ruta_final) and metodo in a]


def issue(numero, clave, estado="open", etiquetas=(), ids=None, anterior=False):
    marca = f"<!-- reescaneo:{clave} -->" if anterior else f"<!-- reescaneo-paquete:{clave} -->"
    vulns = "" if ids is None else f"\n<!-- vulns:{','.join(ids)} -->"
    return {
        "number": numero, "state": estado,
        "labels": [{"name": e} for e in ("reescaneo", *etiquetas)],
        "body": f"{marca}{vulns}\nTexto",
    }


class Pruebas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = Path(self.tmp.name) / "osv.json"
        self.ruta.write_text(json.dumps(REPORTE), encoding="utf-8")
        self.hallazgos = hr.leer_reporte("dependencias", self.ruta)
        self.por_paquete = {h.paquete: h for h in self.hallazgos}

    def tearDown(self):
        self.tmp.cleanup()

    def test_un_hallazgo_por_paquete(self):
        self.assertEqual(sorted(self.por_paquete), ["curl", "starlette", "zlib"])
        starlette = self.por_paquete["starlette"]
        self.assertEqual(starlette.ids, ["CVE-2099-0001", "GHSA-dddd-eeee-ffff"])
        self.assertEqual(starlette.cvss, 7.5)
        self.assertEqual(starlette.severidad, "alta")
        self.assertEqual(starlette.corregida_en, ["0.40.1", "0.41.0"])
        # curl en dos capas: una sola vulnerabilidad.
        self.assertEqual(self.por_paquete["curl"].ids, ["CVE-2099-0003"])
        self.assertEqual(self.por_paquete["zlib"].severidad, "sin-puntaje")
        self.assertFalse(self.por_paquete["zlib"].registrable)

    def test_cuerpo_tiene_los_campos_del_registro(self):
        cuerpo = hr.cuerpo_issue(self.por_paquete["starlette"], CONTEXTO)
        for campo in ("Origen", "Versión afectada", "Evidencia", "Severidad", "Responsable",
                      "Estado", "Tratamiento", "Última detección"):
            self.assertIn(f"| {campo}", cuerpo)
        self.assertIn(f"<!-- reescaneo-paquete:{STARLETTE} -->", cuerpo)
        self.assertIn("<!-- vulns:CVE-2099-0001,GHSA-dddd-eeee-ffff -->", cuerpo)
        self.assertIn("### Vulnerabilidades (2)", cuerpo)

    def test_reporte_ilegible_es_incompleto(self):
        self.ruta.write_text("{}", encoding="utf-8")
        with self.assertRaises(hr.ErrorRegistro):
            hr.leer_reporte("dependencias", self.ruta)

    def test_registro(self):
        curl = "dependencias|Alpine:v3.22|curl"
        gh = GitHubFalso([
            issue(1, STARLETTE, ids=["CVE-2099-0001"]),          # abierto: aparece una nueva
            issue(2, curl, "closed", ids=["CVE-2099-0003"]),      # cerrado y reaparece
            issue(3, "dependencias|npm|vite"),                    # abierto y ausente
            issue(4, "imagen-backend|Debian:12|openssl"),         # otro origen: no se toca
        ])
        resumen = hr.sincronizar(self.hallazgos, {"dependencias"}, CONTEXTO, gh)
        self.assertEqual(resumen, {"nuevos": 0, "actualizados": 1, "reabiertos": 1,
                                   "ya_aceptados": 0, "no_detectados": 1, "informativos": 1,
                                   "reemplazados": 0})
        parches = {a[1].rsplit("/", 1)[1]: e for a, e in gh.llamadas if "PATCH" in a}
        self.assertEqual(parches["2"]["state"], "open")
        self.assertNotIn("state", parches["1"])
        self.assertIn("severidad:alta", parches["1"]["labels"])
        comentario = gh.acciones("issues/1/comments", "POST")[0]["body"]
        self.assertIn("nuevas: GHSA-dddd-eeee-ffff", comentario)
        self.assertEqual(gh.acciones("issues/3/labels", "POST"), [{"labels": ["no-detectado"]}])
        self.assertFalse(any("issues/4" in a[1] for a, _ in gh.llamadas))

    def test_sin_cambios_no_comenta(self):
        gh = GitHubFalso([issue(1, STARLETTE, ids=["CVE-2099-0001", "GHSA-dddd-eeee-ffff"])])
        hr.sincronizar([self.por_paquete["starlette"]], {"dependencias"}, CONTEXTO, gh)
        self.assertEqual(gh.acciones("issues/1/comments", "POST"), [])
        self.assertEqual(len(gh.acciones("issues/1", "PATCH")), 1)

    def test_nuevos_e_informativos(self):
        gh = GitHubFalso([])
        resumen = hr.sincronizar(self.hallazgos, {"dependencias"}, CONTEXTO, gh)
        # starlette y curl se registran; zlib (sin corrección ni puntaje) no.
        self.assertEqual((resumen["nuevos"], resumen["informativos"]), (2, 1))
        titulos = sorted(e["title"] for e in gh.acciones("org/repo/issues", "POST"))
        self.assertEqual(len(titulos), 2)
        self.assertTrue(titulos[1].startswith("[Reescaneo] starlette 0.40.0: 2 vulnerabilidades"))

    def test_aceptado_solo_avisa_si_hay_nuevas(self):
        gh = GitHubFalso([issue(7, STARLETTE, "closed", ["riesgo-aceptado"],
                                ids=["CVE-2099-0001", "GHSA-dddd-eeee-ffff"])])
        hr.sincronizar([self.por_paquete["starlette"]], {"dependencias"}, CONTEXTO, gh)
        self.assertEqual(gh.llamadas[-1][0][0], "label")  # solo etiquetas, nada en #7
        gh = GitHubFalso([issue(7, STARLETTE, "closed", ["riesgo-aceptado"],
                                ids=["CVE-2099-0001"])])
        resumen = hr.sincronizar([self.por_paquete["starlette"]], {"dependencias"}, CONTEXTO, gh)
        self.assertEqual(resumen["ya_aceptados"], 1)
        self.assertEqual(len(gh.acciones("issues/7/comments", "POST")), 1)
        self.assertEqual(gh.acciones("issues/7", "PATCH"), [])

    def test_formato_anterior_se_reemplaza(self):
        gh = GitHubFalso([
            issue(50, f"{STARLETTE}|CVE-2099-0001", anterior=True),
            issue(51, f"{ZLIB}|DEBIAN-CVE-2099-0002", anterior=True),
            issue(52, f"{STARLETTE}|CVE-2099-0009", "closed", anterior=True),
        ])
        resumen = hr.sincronizar(self.hallazgos, {"dependencias"}, CONTEXTO, gh)
        self.assertEqual(resumen["reemplazados"], 2)
        nuevo = gh.acciones("issues/50/comments", "POST")[0]["body"]
        self.assertRegex(nuevo, r"issue agrupado #20[12]")
        self.assertIn("registro agrupado", gh.acciones("issues/51/comments", "POST")[0]["body"])
        cierre = gh.acciones("issues/50", "PATCH")[0]
        self.assertEqual(cierre, {"state": "closed", "state_reason": "not_planned"})
        self.assertFalse(any("issues/52" in a[1] for a, _ in gh.llamadas))


if __name__ == "__main__":
    unittest.main()
