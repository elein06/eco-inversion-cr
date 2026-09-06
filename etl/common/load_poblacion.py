"""
Carga la población por cantón en `cantones.poblacion`.

Por qué existe este archivo aparte de `load_cantones.py`: ese script es de
Integrante 1 y su trabajo es crear las filas (geometría, nombre, provincia,
codigo_ine). La población es un dato de referencia del INEC que no viene en el
GeoJSON y que se carga después, así que se deja como un paso propio en vez de
tocar un script que es de otra persona.

Quién usa esta columna —importa, porque no es solo de una fuente—:

    backend/app/indice.py  _factor_seguridad   delitos por 10 000 habitantes.
                                               Sin población usa el CONTEO
                                               BRUTO, que hace ver peor a los
                                               cantones grandes solo por serlo.
    etl/sicop/factor_inversion.py  sub_monto   monto por habitante. Sin
                                               población cae a monto absoluto y
                                               lo anota en `base_monto`.

Ninguno de los dos se rompe si la columna está vacía: los dos degradan a una
medida absoluta. Pero las dos degradaciones tienen el mismo sesgo —premian o
castigan por tamaño— así que conviene cargarla.

FUENTE DEL DATO
---------------
Este script NO trae números propios ni los inventa: lee un CSV que hay que
bajar del INEC y guardar en `db/`. Se hizo así a propósito, porque un dato de
población escrito a mano en el código no se puede auditar ni citar en la
exposición.

El CSV debe tener al menos estas dos columnas (el orden no importa):

    codigo_ine,poblacion
    101,352381
    102,67155
    ...

`nombre` y `provincia` son opcionales; si vienen, se usan solo para avisar
cuando el nombre del CSV no coincide con el de la base, que es la señal típica
de que el `codigo_ine` está corrido.

Uso:
    python load_poblacion.py --csv ../../db/poblacion_cantones.csv --dry-run
    python load_poblacion.py --csv ../../db/poblacion_cantones.csv \
                             --fuente "INEC, proyecciones 2025" \
                             --url https://inec.cr/...
"""
import argparse
import csv
import os
import sys
import unicodedata

# La consola de Windows usa cp1252 y rompe los nombres con tilde.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_connection  # noqa: E402


def sin_tildes(texto):
    """'Pérez Zeledón' -> 'Perez Zeledon', para comparar nombres sin depender de tildes."""
    return "".join(
        c
        for c in unicodedata.normalize("NFD", str(texto))
        if unicodedata.category(c) != "Mn"
    )


def _clave_nombre(texto):
    return " ".join(sin_tildes(texto).split()).lower()


def _columna(fila, *candidatas):
    """Busca una columna sin depender de mayúsculas, tildes ni espacios."""
    normalizadas = {_clave_nombre(k).replace(" ", "_"): k for k in fila}
    for candidata in candidatas:
        clave = _clave_nombre(candidata).replace(" ", "_")
        if clave in normalizadas:
            return normalizadas[clave]
    return None


def _entero(valor):
    """
    '352 381', '352,381' y '352381' son el mismo número. El INEC publica con
    separador de miles según el formato regional, así que se limpia antes de
    convertir.
    """
    limpio = str(valor).strip().replace(" ", "").replace(",", "").replace(".", "")
    limpio = limpio.replace(" ", "")  # espacio duro
    if not limpio:
        return None
    return int(limpio)


def leer_csv(ruta):
    """Devuelve {codigo_ine: (poblacion, nombre_en_csv)}."""
    with open(ruta, encoding="utf-8-sig", newline="") as fh:
        muestra = fh.read(4096)
        fh.seek(0)
        try:
            dialecto = csv.Sniffer().sniff(muestra, delimiters=",;\t")
        except csv.Error:
            dialecto = csv.excel
        filas = list(csv.DictReader(fh, dialect=dialecto))

    if not filas:
        raise ValueError("El CSV '{}' no tiene filas.".format(ruta))

    col_codigo = _columna(filas[0], "codigo_ine", "codigo", "cod_canton", "dta")
    col_poblacion = _columna(filas[0], "poblacion", "población", "habitantes", "total")
    col_nombre = _columna(filas[0], "canton", "cantón", "nombre")

    if col_codigo is None or col_poblacion is None:
        raise ValueError(
            "El CSV debe traer una columna de código (codigo_ine) y una de "
            "población. Encontradas: {}".format(", ".join(filas[0].keys()))
        )

    datos = {}
    for fila in filas:
        codigo = str(fila[col_codigo]).strip()
        if not codigo:
            continue
        # El INEC publica los códigos con y sin cero a la izquierda ('101' y
        # '0101'); la base usa la forma corta.
        codigo = codigo.lstrip("0") or codigo
        poblacion = _entero(fila[col_poblacion])
        if poblacion is None:
            continue
        nombre = fila[col_nombre].strip() if col_nombre else None
        datos[codigo] = (poblacion, nombre)
    return datos


def cargar(ruta_csv, fuente, url, dry_run):
    datos = leer_csv(ruta_csv)
    print("CSV leído: {} cantones con población".format(len(datos)))

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT canton_id, codigo_ine, nombre, poblacion FROM cantones "
                "ORDER BY codigo_ine"
            )
            cantones = cur.fetchall()

            if not cantones:
                raise RuntimeError(
                    "La tabla `cantones` está vacía. Cárguela primero: "
                    "python load_cantones.py --geojson ../../db/cantones_cr.geojson"
                )

            actualizables = []
            sin_dato = []
            discrepancias = []

            for canton_id, codigo_ine, nombre, poblacion_actual in cantones:
                entrada = datos.get(str(codigo_ine).strip())
                if entrada is None:
                    sin_dato.append((codigo_ine, nombre))
                    continue
                poblacion, nombre_csv = entrada
                if nombre_csv and _clave_nombre(nombre_csv) != _clave_nombre(nombre):
                    discrepancias.append((codigo_ine, nombre, nombre_csv))
                actualizables.append((canton_id, codigo_ine, nombre, poblacion_actual, poblacion))

            if discrepancias:
                print(
                    "\nAviso: {} códigos donde el nombre del CSV no coincide con "
                    "el de la base. Suele significar que el código está "
                    "corrido:".format(len(discrepancias))
                )
                for codigo, en_base, en_csv in discrepancias[:10]:
                    print("  {:<6} base='{}'  csv='{}'".format(codigo, en_base, en_csv))

            if sin_dato:
                print("\n{} cantones sin población en el CSV:".format(len(sin_dato)))
                for codigo, nombre in sin_dato[:15]:
                    print("  {:<6} {}".format(codigo, nombre))

            print("\nSe van a actualizar {} de {} cantones.".format(
                len(actualizables), len(cantones)))
            for _, codigo, nombre, antes, despues in actualizables[:10]:
                print("  {:<6} {:<22} {} -> {:,}".format(
                    codigo, nombre[:22], antes if antes is not None else "NULL", despues))
            if len(actualizables) > 10:
                print("  ... y {} más".format(len(actualizables) - 10))

            if dry_run:
                print("\ndry-run: no se escribió nada en la base.")
                return 0

            if not actualizables:
                print("\nNada que actualizar.")
                return 0

            for canton_id, _, _, _, poblacion in actualizables:
                cur.execute(
                    "UPDATE cantones SET poblacion = %s WHERE canton_id = %s",
                    (poblacion, canton_id),
                )

        # `sincronizaciones` es el mecanismo de trazabilidad del proyecto: una
        # carga de población también tiene que quedar registrada, con su fuente.
        from db import registrar_sincronizacion

        registrar_sincronizacion(
            conn,
            fuente_codigo="SNIT",
            estado="exito",
            registros_procesados=len(actualizables),
            mensaje="poblacion de cantones: {} actualizados desde {}; fuente: {}{}".format(
                len(actualizables),
                os.path.basename(ruta_csv),
                fuente or "no indicada",
                " ({})".format(url) if url else "",
            ),
        )

    print("\nOK: {} cantones con población cargada.".format(len(actualizables)))
    print(
        "\nRecuerde recalcular, porque los factores no se actualizan solos:\n"
        "  cd ../sicop && python sync_sicop.py --calcular-factor\n"
        "  curl -X POST http://localhost:8000/indice-viabilidad/recalcular"
    )
    return len(actualizables)


def main():
    parser = argparse.ArgumentParser(
        description="Carga cantones.poblacion desde un CSV del INEC"
    )
    parser.add_argument(
        "--csv",
        required=True,
        help="CSV con columnas codigo_ine y poblacion (ver el encabezado de este archivo)",
    )
    parser.add_argument(
        "--fuente",
        help='Descripción de la fuente, ej. "INEC, proyecciones distritales 2025"',
    )
    parser.add_argument("--url", help="URL de donde se bajó el CSV, para la trazabilidad")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra qué se actualizaría, sin escribir en la base",
    )
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        parser.error("No existe el archivo '{}'".format(args.csv))

    cargar(args.csv, args.fuente, args.url, args.dry_run)


if __name__ == "__main__":
    main()
