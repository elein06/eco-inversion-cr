"""
Carga de la tabla `cantones` (infraestructura compartida, no es de una sola
fuente OSINT) a partir de un archivo GeoJSON local con los límites
cantonales de Costa Rica.

Por qué existe este script:
La tabla `cantones` es el eje territorial que usan las cuatro fuentes
(SNIT, SICOP, OSM, OIJ) para vincular sus datos. Nadie del reparto original
la tenía asignada explícitamente, así que la resolvemos como parte de nuestra
tarea de OSM ya que dependemos de ella para probar la carga real de
`infraestructura_osm`.

De dónde sacar el archivo GeoJSON (descargarlo manualmente con el navegador;
el acceso a estos dominios no está disponible desde este entorno automatizado):

  Opción recomendada — ArcGIS Hub (datos abiertos, con NOM_PROV/NOM_CANT):
    https://daticos-geotec.opendata.arcgis.com/datasets/249bc8711c33493a90b292b55ed3abad_0
    → botón "Download" → GeoJSON

  Alternativa — GitHub (mismo shape, campos NAME_1/NAME_2):
    https://github.com/maufonsecasdfg/costa-rica-geojson
    → costaricacantones.geojson

Guardá el archivo descargado en, por ejemplo, `db/cantones_cr.geojson`.

IMPORTANTE sobre `codigo_ine`:
Ninguna de las fuentes públicas más accesibles trae el código oficial de la
División Territorial Administrativa (DTA) del INEC en un campo claro. Este
script genera un código PROVISIONAL determinístico (`PP-CC`, provincia y
cantón numerados alfabéticamente) solo para cumplir la restricción NOT NULL
UNIQUE del esquema. Si más adelante alguien encuentra la tabla oficial de
códigos INEC, se puede correr este script de nuevo con --codigos-oficiales
apuntando a un CSV (columnas: provincia,canton,codigo_ine) para reemplazarlos
sin perder las geometrías ya cargadas.

Uso:
    python load_cantones.py --geojson ../../db/cantones_cr.geojson
    python load_cantones.py --geojson ../../db/cantones_cr.geojson --prov-field NAME_1 --canton-field NAME_2
    python load_cantones.py --geojson ../../db/cantones_cr.geojson --codigos-oficiales codigos_ine.csv
"""
import argparse
import csv
import json
import os
import sys

sys.path.append(os.path.dirname(__file__))
from db import get_connection  # noqa: E402

# Nombres de campo más comunes vistos en las fuentes públicas de cantones CR.
CANDIDATOS_PROVINCIA = ["NOM_PROV", "NAME_1", "provincia", "PROVINCIA"]
CANDIDATOS_CANTON = ["NOM_CANT_1", "NOM_CANT", "NAME_2", "canton", "CANTON"]


def detectar_campo(propiedades: dict, candidatos: list[str]) -> str | None:
    for candidato in candidatos:
        if candidato in propiedades:
            return candidato
    return None


def titulo(texto: str) -> str:
    return " ".join(p.capitalize() for p in texto.strip().split())


def cargar_codigos_oficiales(ruta_csv: str) -> dict:
    """Lee un CSV opcional (provincia,canton,codigo_ine) -> {(provincia,canton): codigo}."""
    mapa = {}
    with open(ruta_csv, encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            clave = (titulo(fila["provincia"]), titulo(fila["canton"]))
            mapa[clave] = fila["codigo_ine"].strip()
    return mapa


def cargar(geojson_path: str, prov_field: str | None, canton_field: str | None, codigos_csv: str | None) -> None:
    with open(geojson_path, encoding="utf-8") as f:
        data = json.load(f)

    features = data["features"]
    if not features:
        print("ERROR: el GeoJSON no tiene features.", file=sys.stderr)
        sys.exit(1)

    propiedades_ejemplo = features[0]["properties"]
    prov_field = prov_field or detectar_campo(propiedades_ejemplo, CANDIDATOS_PROVINCIA)
    canton_field = canton_field or detectar_campo(propiedades_ejemplo, CANDIDATOS_CANTON)

    if not prov_field or not canton_field:
        print(
            "ERROR: no pude detectar automáticamente los campos de provincia/cantón.\n"
            f"Campos disponibles en la primera feature: {list(propiedades_ejemplo.keys())}\n"
            "Pasalos explícitamente con --prov-field y --canton-field.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Usando campo de provincia: '{prov_field}' | campo de cantón: '{canton_field}'")

    codigos_oficiales = cargar_codigos_oficiales(codigos_csv) if codigos_csv else {}

    # Orden determinístico para generar el código provisional PP-CC.
    registros = []
    for feat in features:
        prov = titulo(str(feat["properties"][prov_field]))
        cant = titulo(str(feat["properties"][canton_field]))
        registros.append((prov, cant, feat["geometry"]))
    registros.sort(key=lambda r: (r[0], r[1]))

    provincias_ordenadas = sorted({r[0] for r in registros})
    contador_por_provincia: dict[str, int] = {}

    insertados = 0
    actualizados = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            for prov, cant, geometry in registros:
                clave = (prov, cant)
                if clave in codigos_oficiales:
                    codigo_ine = codigos_oficiales[clave]
                    origen_codigo = "oficial (CSV)"
                else:
                    idx_prov = provincias_ordenadas.index(prov) + 1
                    contador_por_provincia[prov] = contador_por_provincia.get(prov, 0) + 1
                    codigo_ine = f"{idx_prov:02d}-{contador_por_provincia[prov]:02d}"
                    origen_codigo = "provisional"

                geojson_geom = json.dumps(geometry)
                cur.execute(
                    """
                    INSERT INTO cantones (codigo_ine, nombre, provincia, geom)
                    VALUES (%s, %s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
                    ON CONFLICT (codigo_ine) DO UPDATE
                        SET nombre = EXCLUDED.nombre,
                            provincia = EXCLUDED.provincia,
                            geom = EXCLUDED.geom
                    RETURNING (xmax = 0) AS fue_insert
                    """,
                    (codigo_ine, cant, prov, geojson_geom),
                )
                fue_insert = cur.fetchone()[0]
                if fue_insert:
                    insertados += 1
                else:
                    actualizados += 1
                print(f"  {codigo_ine} ({origen_codigo}) — {prov} / {cant}")

    print(f"\nOK: {insertados} cantones insertados, {actualizados} actualizados.")
    if not codigos_oficiales:
        print(
            "NOTA: los códigos son PROVISIONALES (no son los códigos oficiales INEC/DTA). "
            "Documentar esto en el README/exposición si alguien pregunta por 'codigo_ine'."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga la tabla cantones desde un GeoJSON local")
    parser.add_argument("--geojson", required=True, help="Ruta al archivo .geojson de cantones de Costa Rica")
    parser.add_argument("--prov-field", help="Nombre del campo de provincia (autodetectado si se omite)")
    parser.add_argument("--canton-field", help="Nombre del campo de cantón (autodetectado si se omite)")
    parser.add_argument(
        "--codigos-oficiales",
        help="CSV opcional (columnas: provincia,canton,codigo_ine) con códigos INEC reales",
    )
    args = parser.parse_args()
    cargar(args.geojson, args.prov_field, args.canton_field, args.codigos_oficiales)


if __name__ == "__main__":
    main()
