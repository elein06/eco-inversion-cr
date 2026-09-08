"""
Carga de los contratos ambientales de SICOP en PostgreSQL — Integrante 2.

Recibe la conexión ya abierta, para que
quien orquesta controle la transacción: si algo falla a mitad de la carga, no
queda media tabla escrita.
"""
import math

from clasificacion import sin_tildes


# Cantones que cambiaron de nombre por ley y que SICOP sigue registrando con el
# nombre derogado en su catálogo de instituciones compradoras. La tabla
# `cantones` viene del IGN vía SNIT y usa los nombres vigentes, así que sin esta
# equivalencia esos cuatro cantones quedarían sin `canton_id` y su inversión
# ambiental no aparecería en el mapa.
#
# Verificado el 2026-09-03 contra el reporte real SV_CONT_0016: son exactamente
# los 4 casos que no resolvían de 96 gobiernos locales. El propio nombre de la
# institución delata el cambio ("MUNICIPALIDAD DE ZARCERO" domiciliada en un
# cantón que SICOP llama "Alfaro Ruiz").
#
#   nombre en SICOP  ->  nombre vigente (IGN)          ley
CANTONES_RENOMBRADOS = {
    "alfaro ruiz": "zarcero",             # Ley 9268 (2014)
    "valverde vega": "sarchi",            # Ley 9440 (2017)
    "aguirre": "quepos",                  # Ley 9331 (2015)
    "leon cortes": "leon cortes castro",  # nombre completo en la capa del IGN
}


def _clave(texto):
    """
    Normaliza un nombre de cantón para comparar: sin tildes, sin espacios
    sobrantes, en minúsculas, y traduciendo los nombres derogados al vigente.
    """
    limpio = " ".join(sin_tildes(str(texto)).split()).lower()
    return CANTONES_RENOMBRADOS.get(limpio, limpio)


def mapa_cantones(conn):
    """
    Trae los 84 cantones y arma dos índices de búsqueda: uno por
    (cantón, provincia) y otro solo por cantón.

    Se usan los dos porque el catálogo de instituciones de SICOP escribe el
    cantón en texto libre, y en Costa Rica hay nombres de cantón que se repiten
    con nombre de provincia (San José, Alajuela, Cartago, Heredia, Puntarenas,
    Limón). Con la provincia se desempata; sin ella, se acepta la coincidencia
    solo si el nombre es único en el país.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT canton_id, nombre, provincia FROM cantones")
        filas = cur.fetchall()

    if not filas:
        raise RuntimeError(
            "La tabla `cantones` está vacía. El ETL del SNIT (Integrante 1) es "
            "el que la llena y va primero: "
            "cd etl/snit && python sync_snit.py --capa cantones"
        )

    por_par = {}
    conteo_nombre = {}
    por_nombre = {}
    for canton_id, nombre, provincia in filas:
        por_par[(_clave(nombre), _clave(provincia))] = canton_id
        clave_nombre = _clave(nombre)
        conteo_nombre[clave_nombre] = conteo_nombre.get(clave_nombre, 0) + 1
        por_nombre[clave_nombre] = canton_id

    # Solo se deja en el índice por nombre lo que es inequívoco.
    por_nombre = {k: v for k, v in por_nombre.items() if conteo_nombre[k] == 1}
    return (por_par, por_nombre)


def resolver_canton_id(mapas, canton, provincia):
    por_par, por_nombre = mapas
    clave_canton = _clave(canton)
    if not clave_canton:
        return None
    canton_id = por_par.get((clave_canton, _clave(provincia)))
    if canton_id is not None:
        return canton_id
    return por_nombre.get(clave_canton)


def _valor(fila, campo, defecto=None):
    valor = fila.get(campo, defecto)
    if valor is None:
        return defecto
    if isinstance(valor, float) and math.isnan(valor):
        return defecto
    return valor


def borrar_periodo(conn, desde, hasta):
    """
    Borra los contratos SICOP del periodo que se va a recargar.

    `contratos_ambientales` no tiene llave natural en el esquema compartido
    (db/schema.sql), así que un upsert no es posible sin tocar ese esquema, que
    es de todo el equipo. Borrar el periodo y volver a insertarlo dentro de la
    misma transacción deja la tabla igual que si se hubiera corrido una sola
    vez, y no afecta a periodos que ya estaban cargados.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM contratos_ambientales
             WHERE fuente_id = (SELECT fuente_id FROM fuentes WHERE codigo = 'SICOP')
               AND fecha_contrato BETWEEN %s AND %s
            """,
            (desde, hasta),
        )
        return cur.rowcount


def cargar_contratos(conn, df, desde=None, hasta=None):
    """
    Inserta el DataFrame que devuelve `normalizacion.construir_dataset`.

    Devuelve (insertados, sin_canton, borrados). `sin_canton` cuenta los
    contratos cuyo cantón no se pudo resolver: se insertan igual con
    canton_id NULL, porque el dato del contrato es válido aunque no se pueda
    ubicar en el mapa, pero quedan contados para poder reportarlos.
    """
    mapas = mapa_cantones(conn)

    borrados = 0
    if desde is not None and hasta is not None:
        borrados = borrar_periodo(conn, desde, hasta)

    insertados = 0
    sin_canton = 0
    with conn.cursor() as cur:
        for _, fila in df.iterrows():
            canton_id = resolver_canton_id(
                mapas, _valor(fila, "canton", ""), _valor(fila, "provincia", "")
            )
            if canton_id is None:
                sin_canton += 1

            fecha = _valor(fila, "fecha_contrato")
            if fecha is not None and hasattr(fecha, "date"):
                fecha = fecha.date()

            cur.execute(
                """
                INSERT INTO contratos_ambientales
                    (fuente_id, canton_id, institucion, municipalidad, monto,
                     moneda, fecha_contrato, descripcion_objeto, categoria_detectada)
                VALUES (
                    (SELECT fuente_id FROM fuentes WHERE codigo = 'SICOP'),
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    canton_id,
                    str(_valor(fila, "institucion", ""))[:500],
                    str(_valor(fila, "municipalidad", ""))[:500] or None,
                    float(_valor(fila, "monto", 0) or 0),
                    str(_valor(fila, "moneda", "CRC"))[:3] or "CRC",
                    fecha,
                    str(_valor(fila, "descripcion_objeto", "")) or None,
                    str(_valor(fila, "categoria_detectada", "")),
                ),
            )
            insertados += 1

    return (insertados, sin_canton, borrados)
