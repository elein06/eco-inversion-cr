"""Autoprueba del registro de hallazgos del reescaneo (ítem 7.6).

Comprueba, sin red ni GitHub, que un reporte de OSV-Scanner produce los
hallazgos esperados y que el registro crea, actualiza, reabre y marca como no
detectados los issues correctos. El workflow la ejecuta antes de registrar.

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

# Forma de un reporte JSON de OSV-Scanner v2 con dos alias de la misma
# vulnerabilidad (un hallazgo) y otra sin puntaje.
REPORTE = {
    "results": [{
        "source": {"path": "/src/backend/requirements.lock", "type": "lockfile"},
        "packages": [
            {
                "package": {"name": "starlette", "version": "0.40.0", "ecosystem": "PyPI"},
                "vulnerabilities": [
                    {"id": "GHSA-aaaa-bbbb-cccc", "summary": "DoS en multipart", "aliases": ["CVE-2099-0001"],
                     "affected": [{"package": {"name": "starlette", "ecosystem": "PyPI"},
                                   "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "0.40.1"}]}]}]},
                    {"id": "PYSEC-2099-1", "aliases": ["CVE-2099-0001"], "affected": []},
                ],
                "groups": [{"ids": ["GHSA-aaaa-bbbb-cccc", "PYSEC-2099-1"], "aliases": ["CVE-2099-0001"], "max_severity": "7.5"}],
            },
            {
                "package": {"name": "zlib", "version": "1.2.13", "ecosystem": "Debian:12"},
                "vulnerabilities": [{"id": "DEBIAN-CVE-2099-0002", "affected": []}],
                "groups": [{"ids": ["DEBIAN-CVE-2099-0002"], "max_severity": ""}],
            },
        ],
    }]
}

CONTEXTO = {"commit": "abc123", "imagenes": {}, "ejecucion": "https://ejemplo/run/1", "fecha": "2026-11-12 12:00 UTC"}


class GitHubFalso(hr.GitHub):
    def __init__(self, issues):
        super().__init__("org/repo", simular=False)
        self.issues = issues
        self.llamadas: list[tuple] = []

    def issues_reescaneo(self):
        return self.issues

    def _gh(self, *args, entrada=None):
        self.llamadas.append((args, entrada))
        return ""

    def acciones(self, ruta_final: str, metodo: str):
        return [e for a, e in self.llamadas if a[1].endswith(ruta_final) and metodo in a]


def issue(numero, clave, estado="open", etiquetas=()):
    return {
        "number": numero, "state": estado,
        "labels": [{"name": e} for e in ("reescaneo", *etiquetas)],
        "body": f"<!-- reescaneo:{clave} -->\nTexto\n<!-- ultima-deteccion -->viejo<!-- /ultima-deteccion -->",
    }


class Pruebas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = Path(self.tmp.name) / "osv.json"
        self.ruta.write_text(json.dumps(REPORTE), encoding="utf-8")
        self.hallazgos = hr.leer_reporte("dependencias", self.ruta)

    def tearDown(self):
        self.tmp.cleanup()

    def test_un_hallazgo_por_grupo_de_alias(self):
        self.assertEqual(len(self.hallazgos), 2)
        starlette = next(h for h in self.hallazgos if h.paquete == "starlette")
        self.assertEqual(starlette.vuln_id, "CVE-2099-0001")
        self.assertEqual(starlette.severidad, "alta")
        self.assertEqual(starlette.corregida_en, ["0.40.1"])
        zlib = next(h for h in self.hallazgos if h.paquete == "zlib")
        self.assertEqual(zlib.severidad, "sin-puntaje")

    def test_cuerpo_tiene_los_campos_del_registro(self):
        cuerpo = hr.cuerpo_issue(self.hallazgos[0], CONTEXTO)
        for campo in ("Origen", "Versión afectada", "Evidencia", "Severidad", "Responsable", "Estado", "Tratamiento"):
            self.assertIn(f"| {campo}", cuerpo)
        self.assertIn("<!-- reescaneo:dependencias|", cuerpo)

    def test_reporte_ilegible_es_incompleto(self):
        self.ruta.write_text("{}", encoding="utf-8")
        with self.assertRaises(hr.ErrorRegistro):
            hr.leer_reporte("dependencias", self.ruta)

    def test_registro(self):
        clave_starlette = "dependencias|PyPI|starlette|CVE-2099-0001"
        clave_zlib = "dependencias|Debian:12|zlib|DEBIAN-CVE-2099-0002"
        gh = GitHubFalso([
            issue(1, clave_starlette),                                       # abierto y presente
            issue(2, clave_zlib, "closed"),                                   # cerrado y reaparece
            issue(3, "dependencias|npm|vite|CVE-2099-0003"),                  # abierto y ausente
            issue(4, "imagen-backend|Debian:12|openssl|CVE-2099-0004"),       # otro origen: no se toca
            issue(5, "dependencias|npm|esbuild|CVE-2099-0005", "closed", ["falso-positivo"]),
        ])
        resumen = hr.sincronizar(self.hallazgos, {"dependencias"}, CONTEXTO, gh)
        self.assertEqual(resumen, {"nuevos": 0, "actualizados": 1, "reabiertos": 1,
                                   "ya_aceptados": 0, "no_detectados": 1, "informativos": 0})
        parches = {a[1].rsplit("/", 1)[1]: e for a, e in gh.llamadas if "PATCH" in a}
        self.assertEqual(parches["2"]["state"], "open")
        self.assertNotIn("state", parches["1"])
        self.assertIn("abc123", parches["1"]["body"])
        self.assertNotIn("viejo", parches["1"]["body"])
        self.assertEqual(gh.acciones("issues/3/labels", "POST"), [{"labels": ["no-detectado"]}])
        self.assertFalse(any("issues/4" in a[1] for a, _ in gh.llamadas))

    def test_nuevo_y_aceptado(self):
        clave_zlib = "dependencias|Debian:12|zlib|DEBIAN-CVE-2099-0002"
        gh = GitHubFalso([issue(7, clave_zlib, "closed", ["riesgo-aceptado"])])
        resumen = hr.sincronizar(self.hallazgos, {"dependencias"}, CONTEXTO, gh)
        self.assertEqual(resumen["nuevos"], 1)
        self.assertEqual(resumen["ya_aceptados"], 1)
        creado = gh.acciones("org/repo/issues", "POST")[0]
        self.assertIn("severidad:alta", creado["labels"])
        self.assertIn("pendiente-investigacion", creado["labels"])
        self.assertFalse(any("PATCH" in a and a[1].endswith("/7") for a, _ in gh.llamadas))


    def test_sin_correccion_y_cvss_bajo_es_informativo(self):
        # zlib: sin corrección y sin puntaje. No se crea issue, y tampoco cuenta
        # como "no detectado" para un issue que ya existiera.
        gh = GitHubFalso([])
        resumen = hr.sincronizar(self.hallazgos, {"dependencias"}, CONTEXTO, gh)
        self.assertEqual((resumen["nuevos"], resumen["informativos"]), (1, 1))
        titulos = [e["title"] for e in gh.acciones("org/repo/issues", "POST")]
        self.assertEqual(len(titulos), 1)
        self.assertIn("starlette", titulos[0])


if __name__ == "__main__":
    unittest.main()
