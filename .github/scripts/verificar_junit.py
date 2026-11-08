"""Falla si un reporte JUnit no demuestra que las pruebas se ejecutaron.

pytest termina con éxito aunque omita pruebas, y una prueba omitida no cuenta
como aprobada: sin esta comprobación, perder TEST_DATABASE_URL dejaría el CI
en verde sin haber probado la API.
"""

import sys
import xml.etree.ElementTree as ET


def main(ruta: str) -> int:
    raiz = ET.parse(ruta).getroot()
    suites = [raiz] if raiz.tag == "testsuite" else raiz.findall("testsuite")
    total = sum(int(s.get("tests", 0)) for s in suites)
    omitidas = sum(int(s.get("skipped", 0)) for s in suites)

    if total == 0:
        print("ERROR: el reporte no contiene pruebas.")
        return 1
    if omitidas:
        print(f"ERROR: {omitidas} de {total} pruebas se omitieron.")
        return 1
    print(f"OK: {total} pruebas ejecutadas, ninguna omitida.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
