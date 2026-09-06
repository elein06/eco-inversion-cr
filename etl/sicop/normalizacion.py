"""
Normalización de los reportes de SICOP a filas de `contratos_ambientales`
— Integrante 2.

El problema que resuelve este archivo: ningún reporte de SICOP tiene por sí
solo los cuatro datos que el proyecto necesita (institución, cantón, monto y
descripción). Están repartidos y hay que unirlos:

    contratos (SV_CONT_0014)          NRO_CONTRATO, SECUENCIA, NRO_SICOP,
                                      FECHA_NOTIFICACION
              |
              |  NRO_CONTRATO + SECUENCIA
              v
    líneas del contrato (7.2)         CANTIDAD_CONTRATADA, PRECIO_UNITARIO,
                                      TIPO_MONEDA  -> de aquí sale el MONTO
              |
              |  NRO_SICOP
              v
    carteles (SV_CONT_0009)           CEDULA_INSTITUCION, DESCRIPCION
                                      -> de aquí sale el TEXTO que se clasifica
              |
              |  CEDULA_INSTITUCION = CEDULA
              v
    instituciones (SV_CONT_0016)      NOMBRE_INSTITUCION, PROVINCIA, CANTON
                                      -> de aquí sale el CANTÓN

El cantón sale del catálogo de instituciones y no de partir el nombre de la
municipalidad con una regex, que era lo que planteaba el diseño original.

Los nombres de columna se resuelven de forma tolerante (mayúsculas, tildes,
espacios en vez de guión bajo) porque el mismo reporte no siempre viene
idéntico entre formatos csv, xlsx y json.
"""
import io
import json
import os
import re
import zipfile

import pandas as pd

from clasificacion import clasificar, sin_tildes
from reportes import COLUMNAS

# Instituciones que cuentan como gobierno local. El Factor de Inversión
# Municipal mide apoyo institucional del cantón, así que se restringe a la
# municipalidad y a los concejos municipales de distrito; una compra del ICE o
# del AyA está domiciliada en su propio cantón, no donde ejecuta la obra, y
# contarla distorsionaría el índice. Ver la nota de alcance en docs/sicop.md.
PATRON_MUNICIPAL = re.compile(
    r"\b(municipalidad|concejo municipal|federacion.*municipal)", re.IGNORECASE
)

# Tablas que vienen dentro de los zip de SICOP y que el proyecto reconoce pero
# no usa. Se listan para que el ETL las reporte como "reconocida, no se usa" en
# vez de como archivo desconocido, que haría pensar que se está perdiendo algo.
TABLAS_NO_USADAS = {"carteles_lineas"}


# ------------------------------------------------------------------
# Lectura de archivos
# ------------------------------------------------------------------


def normalizar_nombre_columna(nombre):
    """'Descripción del objeto' -> 'DESCRIPCION_DEL_OBJETO'."""
    limpio = sin_tildes(str(nombre)).strip().upper()
    limpio = re.sub(r"[^A-Z0-9]+", "_", limpio)
    return limpio.strip("_")


def normalizar_columnas(df):
    df = df.copy()
    df.columns = [normalizar_nombre_columna(c) for c in df.columns]
    return df


def columna(df, *candidatas):
    """
    Devuelve el nombre real de la primera columna candidata que exista, o None.
    Permite tolerar que SICOP renombre 'NRO_CONTRATO' a 'NUMERO_CONTRATO' entre
    formatos sin que se caiga el ETL.
    """
    existentes = set(df.columns)
    for candidata in candidatas:
        clave = normalizar_nombre_columna(candidata)
        if clave in existentes:
            return clave
    return None


def _leer_bytes(nombre, datos):
    """Lee un archivo suelto (ya en memoria) a DataFrame según su extensión."""
    minusculas = nombre.lower()
    if minusculas.endswith(".csv") or minusculas.endswith(".txt"):
        # SICOP exporta en UTF-8 con BOM y separador coma; algunos reportes
        # vienen en latin-1, así que se intentan ambos antes de rendirse.
        for codificacion in ("utf-8-sig", "latin-1"):
            try:
                return pd.read_csv(
                    io.BytesIO(datos),
                    encoding=codificacion,
                    sep=None,
                    engine="python",
                    dtype=str,
                )
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
        raise ValueError("No se pudo leer el CSV '{}'".format(nombre))
    if minusculas.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(datos), dtype=str)
    if minusculas.endswith(".json"):
        contenido = json.loads(datos.decode("utf-8-sig"))
        if isinstance(contenido, dict):
            # Los json de SICOP envuelven las filas en una sola llave; se toma
            # la primera lista que aparezca.
            for valor in contenido.values():
                if isinstance(valor, list):
                    contenido = valor
                    break
        return pd.DataFrame(contenido, dtype=str)
    raise ValueError("Extensión no soportada: '{}'".format(nombre))


def cargar_archivo(ruta):
    """
    Lee un archivo bajado de SICOP y devuelve [(nombre_interno, DataFrame)].

    Los reportes que el diccionario numera como 7 y 7.2 (contrato y líneas del
    contrato) se descargan juntos, así que un mismo archivo puede ser un zip
    con varias tablas dentro. Se devuelven todas y luego `identificar` decide
    cuál es cuál.
    """
    if not os.path.exists(ruta):
        raise FileNotFoundError("No existe el archivo '{}'".format(ruta))

    # Ojo: `zipfile.is_zipfile` dice que sí para un .xlsx, porque un libro de
    # Excel es literalmente un zip. Por eso la extensión manda: solo se trata
    # como paquete de varias tablas lo que no es una hoja de cálculo.
    es_hoja = ruta.lower().endswith((".xlsx", ".xls"))
    if not es_hoja and zipfile.is_zipfile(ruta):
        tablas = []
        with zipfile.ZipFile(ruta) as zf:
            for interno in zf.namelist():
                if interno.endswith("/"):
                    continue
                try:
                    tablas.append(
                        (interno, normalizar_columnas(_leer_bytes(interno, zf.read(interno))))
                    )
                except ValueError:
                    continue
        if not tablas:
            raise ValueError("El zip '{}' no trae tablas legibles".format(ruta))
        return tablas

    with open(ruta, "rb") as archivo:
        datos = archivo.read()
    return [(os.path.basename(ruta), normalizar_columnas(_leer_bytes(ruta, datos)))]


def identificar(df):
    """
    Adivina qué reporte es un DataFrame a partir de sus columnas. Se usa el
    conjunto de columnas y no el nombre del archivo, porque el nombre que manda
    SICOP en Content-Disposition no es estable.

    Cada campo se prueba contra varios nombres posibles. No es paranoia: el
    Diccionario de Datos oficial documenta los nombres INTERNOS de los campos
    (`NRO_SICOP`, `CANTIDAD_CONTRATADA`, `TIPO_CAMBIO_CRC`), pero el CSV que
    entrega el módulo trae encabezados legibles y distintos ("Número SICOP",
    "Cantidad", "Tipo Cambio"). Se aceptan las dos formas.
    """
    if columna(df, "CEDULA", "CEDULA_INSTITUCION") and columna(
        df, "NOMBRE_INSTITUCION", "NOMBRE_DE_LA_INSTITUCION", "INSTITUCION"
    ):
        return "instituciones"

    # El cartel identifica a la institución con `CEDULA` a secas, igual que el
    # catálogo de instituciones; lo que los distingue es que el cartel trae
    # DESCRIPCION y no el nombre de la institución.
    if columna(df, "DESCRIPCION", "DESCRIPCION_DEL_PROCEDIMIENTO") and columna(
        df, "CEDULA_INSTITUCION", "CEDULA_DE_LA_INSTITUCION", "CEDULA"
    ):
        return "carteles"

    # Líneas del CARTEL: traen el precio ESTIMADO, no el contratado. Se
    # reconocen aparte para no confundirlas con las líneas del contrato —de las
    # que sí sale el monto— y para que el ETL no las reporte como un archivo
    # desconocido. El proyecto no las usa: un precio estimado no es plata
    # comprometida.
    if columna(df, "PRECIO_UNITARIO_ESTIMADO"):
        return "carteles_lineas"

    if columna(df, "PRECIO_UNITARIO") and columna(
        df, "CANTIDAD_CONTRATADA", "CANTIDAD"
    ):
        return "contratos_lineas"
    if columna(df, "NRO_CONTRATO", "NUMERO_CONTRATO") and columna(
        df, "FECHA_NOTIFICACION", "FECHA_DE_NOTIFICACION"
    ):
        return "contratos"
    return None


def cargar_tablas(rutas):
    """
    Lee varios archivos y devuelve {tipo_reporte: DataFrame}. Si un tipo
    aparece en más de un archivo (por ejemplo, dos rangos de fechas), se
    concatenan y se eliminan las filas repetidas.

    La deduplicación no es opcional. `--cargar` sin `--archivo` toma todo
    `data/`, y ahí suele quedar más de una descarga del mismo reporte con
    rangos que se solapan: una prueba corta y la buena, o dos corridas
    semanales. Sin deduplicar, el mismo contrato entra dos veces y el monto del
    cantón se duplica sin que nada avise. Se comprobó: con un reporte de prueba
    de 735 contratos junto al bueno de 19 157, la tabla quedaba en 19 892.

    Se comparan las filas completas, no una llave: dos descargas del mismo
    contrato traen exactamente los mismos valores en todas las columnas.
    """
    acumulado = {}
    for ruta in rutas:
        for nombre_interno, df in cargar_archivo(ruta):
            tipo = identificar(df)
            if tipo in TABLAS_NO_USADAS:
                print(
                    "  {:<18} {:>7} filas  <- {}  (reconocida, no se usa)".format(
                        tipo, len(df), nombre_interno
                    )
                )
                continue
            if tipo is None:
                print(
                    "  aviso: '{}' no coincide con ningún reporte conocido "
                    "(columnas: {})".format(
                        nombre_interno, ", ".join(list(df.columns)[:8])
                    )
                )
                continue
            print(
                "  {:<18} {:>7} filas  <- {}".format(tipo, len(df), nombre_interno)
            )
            if tipo in acumulado:
                antes = len(acumulado[tipo]) + len(df)
                acumulado[tipo] = pd.concat(
                    [acumulado[tipo], df], ignore_index=True
                ).drop_duplicates(ignore_index=True)
                repetidas = antes - len(acumulado[tipo])
                if repetidas:
                    print(
                        "      {} filas repetidas descartadas (descargas que se "
                        "solapan)".format(repetidas)
                    )
            else:
                acumulado[tipo] = df
    return acumulado


# ------------------------------------------------------------------
# Cálculo del monto
# ------------------------------------------------------------------


def _numero(serie):
    """
    Convierte a número tolerando el formato de SICOP: separador de miles con
    coma o punto según el reporte, y vacíos como cadena vacía.
    """
    if serie is None:
        return None
    texto = serie.astype(str).str.strip()
    # Si hay coma y punto, la coma es separador de miles.
    con_ambos = texto.str.contains(",") & texto.str.contains(r"\.")
    texto = texto.mask(con_ambos, texto.str.replace(",", "", regex=False))
    # Si solo hay coma, es el separador decimal.
    solo_coma = texto.str.contains(",") & ~texto.str.contains(r"\.")
    texto = texto.mask(solo_coma, texto.str.replace(",", ".", regex=False))
    return pd.to_numeric(texto, errors="coerce").fillna(0.0)


def montos_por_contrato(df_lineas):
    """
    Suma las líneas de cada contrato y devuelve un DataFrame con
    NRO_CONTRATO, SECUENCIA, monto, moneda.

    Fórmula por línea, siguiendo los campos del diccionario de datos:

        monto = cantidad * precio_unitario - descuento
                + iva + otros_impuestos + acarreos

    Cuando la moneda de la línea no es colones y viene TIPO_CAMBIO_CRC, el
    monto se convierte a colones con ese tipo de cambio, que es el que SICOP
    registró en el contrato. Así el índice compara montos comparables sin
    depender de una fuente de tipo de cambio externa (el BCCR quedó fuera del
    proyecto justamente para no tramitar su token).
    """
    df = df_lineas
    col_contrato = columna(df, "NRO_CONTRATO", "NUMERO_CONTRATO")
    col_secuencia = columna(df, "SECUENCIA")
    if col_contrato is None:
        raise ValueError(
            "Las líneas de contrato no traen NRO_CONTRATO. Columnas: {}".format(
                list(df.columns)
            )
        )

    cantidad = _numero(df[columna(df, "CANTIDAD_CONTRATADA", "CANTIDAD")])
    precio = _numero(df[columna(df, "PRECIO_UNITARIO")])
    bruto = cantidad * precio

    for nombre, signo in (
        ("DESCUENTO", -1),
        ("IVA", 1),
        ("OTROS_IMPUESTOS", 1),
        ("ACARREOS", 1),
    ):
        col = columna(df, nombre)
        if col is not None:
            bruto = bruto + signo * _numero(df[col])

    col_moneda = columna(df, "TIPO_MONEDA", "MONEDA")
    moneda = (
        df[col_moneda].astype(str).str.strip().str.upper()
        if col_moneda
        else pd.Series(["CRC"] * len(df), index=df.index)
    )
    moneda = moneda.replace({"": "CRC", "NAN": "CRC", "NONE": "CRC"})

    col_cambio = columna(df, "TIPO_CAMBIO_CRC", "TIPO_CAMBIO")
    if col_cambio is not None:
        cambio = _numero(df[col_cambio])

        # SICOP deja el tipo de cambio en 0 en más de la mitad de las líneas en
        # moneda extranjera (947 de 1 768 en el reporte de contratos de
        # 2026-06 a 2026-09). Sin un respaldo, esos montos se quedarían en
        # dólares o euros y después se sumarían junto a los colones como si
        # fueran la misma unidad, inflando el factor del cantón.
        #
        # El respaldo NO viene de una fuente externa —el BCCR quedó fuera del
        # proyecto para no tramitar su token—: se usa la MEDIANA de los tipos
        # de cambio que el propio archivo sí trae para esa moneda. Es del mismo
        # periodo que los contratos y queda auditable dentro del dato.
        medianas = {}
        for divisa in moneda[moneda != "CRC"].unique():
            positivos = cambio[(moneda == divisa) & (cambio > 0)]
            if len(positivos):
                medianas[divisa] = float(positivos.median())

        cambio_efectivo = cambio.copy()
        for divisa, mediana in medianas.items():
            faltante = (moneda == divisa) & (cambio <= 0)
            cambio_efectivo = cambio_efectivo.mask(faltante, mediana)

        aplicable = (moneda != "CRC") & (cambio_efectivo > 0)
        bruto = bruto.mask(aplicable, bruto * cambio_efectivo)
        moneda = moneda.mask(aplicable, "CRC")

        # Lo que ni así se pudo convertir se deja en su moneda original. No se
        # descarta —el contrato existe— pero `v_factor_inversion` solo suma
        # colones, así que no contamina el puntaje.
        sin_convertir = int(((moneda != "CRC")).sum())
        if sin_convertir:
            print(
                "  aviso: {} líneas quedaron sin convertir a colones (SICOP no "
                "trae tipo de cambio para su moneda). Se cargan en su moneda "
                "original y no suman al factor.".format(sin_convertir)
            )

    agrupado = pd.DataFrame(
        {
            # OJO: en el archivo de líneas, la columna "Nro Contrato" NO trae el
            # número de contrato sino el IDENTIFICADOR del contrato (CE2026...).
            # El Diccionario de Datos no lo aclara y llama NRO_CONTRATO a las
            # dos cosas. Se comprobó sobre el reporte real: cruzando por
            # NRO_CONTRATO la intersección es 0; cruzando por IDENTIFICADOR son
            # 18 527 de 19 157 contratos.
            "CLAVE_CONTRATO": df[col_contrato].astype(str).str.strip(),
            "SECUENCIA_NORM": (
                _secuencia(df[col_secuencia])
                if col_secuencia
                else pd.Series(["0"] * len(df), index=df.index)
            ),
            "monto": bruto,
            "moneda": moneda,
        }
    )
    return (
        agrupado.groupby(["CLAVE_CONTRATO", "SECUENCIA_NORM"], as_index=False)
        .agg(monto=("monto", "sum"), moneda=("moneda", "first"))
    )


# ------------------------------------------------------------------
# Unión de las cuatro tablas
# ------------------------------------------------------------------


def _secuencia(serie):
    """
    Normaliza la secuencia del contrato. El mismo campo viene con ceros a la
    izquierda en el archivo de líneas ('00', '01') y sin ellos en el de
    contratos ('0', '1'), así que sin esto el join no cruza ni una fila.
    """
    return (
        serie.astype(str).str.strip().str.lstrip("0").replace({"": "0", "nan": "0"})
    )


def _cedula(serie):
    """Normaliza cédulas jurídicas a solo dígitos, para que el join no falle
    por un guión de diferencia entre reportes."""
    return serie.astype(str).str.replace(r"\D", "", regex=True).str.strip()


def _texto_limpio(serie):
    """
    Deja el texto con espacios normales.

    SICOP manda las descripciones con espacio duro (U+00A0) en vez de espacio
    común. En la terminal se ve igual, pero el navegador no puede cortar la
    línea en un espacio duro: las descripciones largas terminan partidas a la
    mitad de una palabra en el panel del mapa. También colapsa los saltos de
    línea y los espacios repetidos que traen algunos carteles.
    """
    return (
        serie.astype(str)
        .str.replace("\u00a0", " ", regex=False)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )


def construir_dataset(tablas, solo_municipalidades=True):
    """
    Une contratos + líneas + carteles + instituciones, clasifica y devuelve el
    DataFrame listo para cargar en `contratos_ambientales`.

    Devuelve (df_ambientales, estadisticas) donde `estadisticas` lleva la
    cuenta de cuántas filas se perdieron en cada paso. Esa cuenta es parte del
    entregable: sin ella no se puede decir si la fuente aportó poco porque hay
    poca inversión ambiental o porque el ETL botó filas.
    """
    faltantes = [t for t in ("contratos", "carteles", "instituciones") if t not in tablas]
    if faltantes:
        raise ValueError(
            "Faltan reportes para poder unir: {}. Bájelos con "
            "'python sync_sicop.py --solicitar --todos'.".format(", ".join(faltantes))
        )

    contratos = tablas["contratos"]
    carteles = tablas["carteles"]
    instituciones = tablas["instituciones"]
    stats = {"contratos": len(contratos), "carteles": len(carteles),
             "instituciones": len(instituciones)}

    # --- 1. cabecera del contrato -------------------------------------
    col_contrato = columna(contratos, "NRO_CONTRATO", "NUMERO_CONTRATO")
    col_ident = columna(contratos, "IDENTIFICADOR")
    col_sicop = columna(contratos, "NRO_SICOP", "NUMERO_SICOP")
    col_fecha = columna(contratos, "FECHA_NOTIFICACION", "FECHA_DE_NOTIFICACION")
    col_secuencia = columna(contratos, "SECUENCIA")
    if col_contrato is None or col_sicop is None:
        raise ValueError(
            "El reporte de contratos no trae NRO_CONTRATO/NRO_SICOP. "
            "Columnas: {}".format(list(contratos.columns))
        )

    df = pd.DataFrame(
        {
            "NRO_CONTRATO": contratos[col_contrato].astype(str).str.strip(),
            # Llave hacia las líneas del contrato: el archivo de líneas guarda
            # el IDENTIFICADOR bajo el nombre "Nro Contrato". Si el reporte no
            # trajera IDENTIFICADOR, se cae al número de contrato para no
            # romper, aunque entonces el join no cruce.
            "CLAVE_CONTRATO": (
                contratos[col_ident].astype(str).str.strip()
                if col_ident
                else contratos[col_contrato].astype(str).str.strip()
            ),
            "SECUENCIA": (
                contratos[col_secuencia].astype(str).str.strip()
                if col_secuencia
                else ""
            ),
            "SECUENCIA_NORM": (
                _secuencia(contratos[col_secuencia])
                if col_secuencia
                else pd.Series(["0"] * len(contratos), index=contratos.index)
            ),
            "NRO_SICOP": contratos[col_sicop].astype(str).str.strip(),
            "fecha_contrato": (
                pd.to_datetime(contratos[col_fecha], errors="coerce", dayfirst=True)
                if col_fecha
                else pd.NaT
            ),
        }
    )

    # --- 2. monto, desde las líneas del contrato ----------------------
    if "contratos_lineas" in tablas:
        montos = montos_por_contrato(tablas["contratos_lineas"])
        df = df.merge(
            montos, on=["CLAVE_CONTRATO", "SECUENCIA_NORM"], how="left"
        )
        stats["contratos_sin_lineas"] = int(df["monto"].isna().sum())
        df["monto"] = df["monto"].fillna(0.0)
        df["moneda"] = df["moneda"].fillna("CRC")
    else:
        # Sin el reporte de líneas no hay monto. Se sigue adelante con monto 0
        # para poder contar contratos, pero se avisa fuerte: el Factor de
        # Inversión quedaría plano.
        print(
            "  AVISO: no se encontraron las líneas de contrato. Los montos "
            "quedan en 0 y el Factor de Inversión no será representativo."
        )
        df["monto"] = 0.0
        df["moneda"] = "CRC"
        stats["contratos_sin_lineas"] = len(df)

    # --- 3. descripción e institución, desde el cartel ----------------
    col_c_sicop = columna(carteles, "NRO_SICOP", "NUMERO_SICOP")
    col_c_ced = columna(
        carteles, "CEDULA_INSTITUCION", "CEDULA_DE_LA_INSTITUCION", "CEDULA"
    )
    col_c_desc = columna(carteles, "DESCRIPCION", "DESCRIPCION_DEL_PROCEDIMIENTO")
    if col_c_desc is None:
        raise ValueError(
            "El reporte de carteles no trae DESCRIPCION, que es la columna "
            "sobre la que se clasifica. Columnas: {}".format(list(carteles.columns))
        )
    resumen_carteles = pd.DataFrame(
        {
            "NRO_SICOP": carteles[col_c_sicop].astype(str).str.strip(),
            "cedula": _cedula(carteles[col_c_ced]),
            "descripcion_objeto": _texto_limpio(carteles[col_c_desc]),
        }
    ).drop_duplicates(subset=["NRO_SICOP"])

    antes = len(df)
    df = df.merge(resumen_carteles, on="NRO_SICOP", how="inner")
    stats["contratos_sin_cartel"] = antes - len(df)

    # --- 4. cantón, desde el catálogo de instituciones ----------------
    col_i_ced = columna(instituciones, "CEDULA", "CEDULA_INSTITUCION")
    col_i_nom = columna(
        instituciones, "NOMBRE_INSTITUCION", "NOMBRE_DE_LA_INSTITUCION", "INSTITUCION"
    )
    col_i_prov = columna(instituciones, "PROVINCIA")
    col_i_cant = columna(instituciones, "CANTON")
    resumen_inst = pd.DataFrame(
        {
            "cedula": _cedula(instituciones[col_i_ced]),
            "institucion": _texto_limpio(instituciones[col_i_nom]),
            "provincia": (
                instituciones[col_i_prov].astype(str).str.strip()
                if col_i_prov
                else ""
            ),
            "canton": (
                instituciones[col_i_cant].astype(str).str.strip() if col_i_cant else ""
            ),
        }
    ).drop_duplicates(subset=["cedula"])

    antes = len(df)
    df = df.merge(resumen_inst, on="cedula", how="inner")
    stats["contratos_sin_institucion"] = antes - len(df)

    # --- 5. filtro de gobierno local ----------------------------------
    if solo_municipalidades:
        antes = len(df)
        df = df[df["institucion"].apply(lambda t: bool(PATRON_MUNICIPAL.search(sin_tildes(t))))]
        stats["descartados_no_municipales"] = antes - len(df)

    # --- 6. clasificación ambiental -----------------------------------
    clasificado = df["descripcion_objeto"].apply(clasificar)
    df = df.assign(
        categoria_detectada=[c[0] for c in clasificado],
        palabra_detectada=[c[1] for c in clasificado],
    )
    stats["evaluados"] = len(df)
    ambientales = df[df["categoria_detectada"].notna()].copy()
    stats["ambientales"] = len(ambientales)
    stats["no_ambientales"] = len(df) - len(ambientales)

    # `municipalidad` es el nombre de la institución compradora; se guarda
    # aparte de `institucion` porque el esquema compartido tiene las dos
    # columnas y el frontend muestra la municipalidad.
    ambientales["municipalidad"] = ambientales["institucion"]
    return (ambientales, stats)


def columnas_esperadas(tipo):
    """Columnas que el diccionario de datos documenta para un reporte."""
    return COLUMNAS.get(tipo, [])
