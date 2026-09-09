"""
Cálculo del Índice de Viabilidad (0-100) por cantón, como suma ponderada de
cuatro factores, uno por fuente OSINT:

    Índice = peso_ambiental     × Factor Ambiental     (SNIT)
           + peso_inversion     × Factor de Inversión   (SICOP)
           + peso_conectividad  × Factor de Conectividad (OSM)
           + peso_seguridad     × Factor de Seguridad    (OIJ)

Los pesos viven en app.config.settings (no hardcodeados aquí) y se guardan
junto al resultado en `indice_viabilidad.pesos_usados`, para poder mostrar
en la exposición exactamente qué se usó en cada cálculo.
"""
import json

from psycopg2.extensions import cursor as Cursor

from app.config import settings


def _factor_ambiental(cur: Cursor) -> dict[int, float]:
    """
    Factor Ambiental (SNIT) — responsable: Integrante 1.

    Lee la vista materializada v_factor_ambiental, que calcula el ETL del SNIT
    en `etl/snit/factor_ambiental.py`. No recalcula nada aquí: ese cruce
    espacial tarda unos 5 minutos y dejaría la API colgada en cada llamada.

    El puntaje combina las tres capas del SNIT con pesos internos propios
    (50% áreas protegidas, 30% corredores biológicos, 20% hidrografía) y una
    banda para las áreas protegidas: un cantón sin nada protegido no ofrece
    entorno natural, y uno casi enteramente protegido no deja terreno donde
    instalarse legalmente. El detalle está en docs/snit.md.

    Si la vista aún no existe —porque nadie ha corrido el ETL del SNIT en esta
    base— devuelve un dict vacío y `calcular_y_guardar_indices` asigna 0.0.
    """
    cur.execute("SELECT to_regclass('v_factor_ambiental') IS NOT NULL AS existe")
    if not cur.fetchone()["existe"]:
        return {}

    cur.execute("SELECT canton_id, factor_ambiental FROM v_factor_ambiental")
    return {
        fila["canton_id"]: float(fila["factor_ambiental"]) for fila in cur.fetchall()
    }


def _factor_inversion(cur: Cursor) -> dict[int, float]:
    """
    Factor de Inversión Municipal (SICOP) — responsable: Integrante 2.

    Lee la vista `v_factor_inversion`, que crea el ETL de SICOP en
    `etl/sicop/factor_inversion.py`. No recalcula nada aquí: el puntaje combina
    monto por habitante, cantidad de contratos y diversidad de categorías con
    pesos internos propios (50/30/20), y los dos primeros se normalizan con
    PERCENT_RANK porque el gasto municipal tiene cola muy larga. El detalle
    está en docs/sicop.md.

    Solo se suman los contratos en colones: uno que quedó en dólares porque
    SICOP no trajo tipo de cambio no se puede sumar sin mentir sobre el monto.

    Si la vista aún no existe —porque nadie ha corrido `sync_sicop.py
    --calcular-factor` en esta base— devuelve un dict vacío y
    `calcular_y_guardar_indices` asigna 0.0.
    """
    cur.execute("SELECT to_regclass('v_factor_inversion') IS NOT NULL AS existe")
    if not cur.fetchone()["existe"]:
        return {}

    cur.execute("SELECT canton_id, factor_inversion FROM v_factor_inversion")
    return {
        fila["canton_id"]: float(fila["factor_inversion"]) for fila in cur.fetchall()
    }


def _factor_conectividad(cur: Cursor) -> dict[int, float]:
    """
    Factor de Conectividad (OSM) — responsable: Integrante 3.

    Lee la vista `v_factor_conectividad`, que crea el ETL de OSM en
    `etl/osm/factor_conectividad.py`. No recalcula nada aquí: la
    normalización min-max ya vive en la vista, sobre los 84 cantones (con y
    sin POIs), no solo sobre los que tienen datos — ver el porqué en ese
    archivo. El detalle está en docs/osm.md.

    Si la vista aún no existe —porque nadie ha corrido `sync_osm.py
    --calcular-factor` en esta base— devuelve un dict vacío y
    `calcular_y_guardar_indices` asigna 0.0.
    """
    cur.execute("SELECT to_regclass('v_factor_conectividad') IS NOT NULL AS existe")
    if not cur.fetchone()["existe"]:
        return {}

    cur.execute("SELECT canton_id, factor_conectividad FROM v_factor_conectividad")
    return {
        fila["canton_id"]: float(fila["factor_conectividad"]) for fila in cur.fetchall()
    }


def _factor_seguridad(cur: Cursor) -> dict[int, float]:
    """
    Factor de Seguridad (OIJ) — responsable: Integrante 4.

    Lee la vista `v_factor_seguridad`, que crea el ETL del OIJ en
    `etl/oij/factor_seguridad.py`. No recalcula nada aquí: es el inverso de
    la tasa de incidencia delictiva (por 10 000 habitantes), normalizada
    min-max contra los 84 cantones (con y sin datos) — igual arquitectura
    que ambiental, inversión y conectividad. El detalle está en docs/oij.md.

    Si la vista aún no existe —porque nadie ha corrido `sync_oij.py
    --calcular-factor` en esta base— devuelve un dict vacío y
    `calcular_y_guardar_indices` asigna 0.0. Antes de este cambio, este
    factor SIEMPRE devolvía algo (50 para todos, por falta de variación) aun
    sin haber corrido el ETL del OIJ ni una sola vez — ver el aviso de
    cambio de comportamiento en `etl/oij/factor_seguridad.py`.
    """
    cur.execute("SELECT to_regclass('v_factor_seguridad') IS NOT NULL AS existe")
    if not cur.fetchone()["existe"]:
        return {}

    cur.execute("SELECT canton_id, factor_seguridad FROM v_factor_seguridad")
    return {
        fila["canton_id"]: float(fila["factor_seguridad"]) for fila in cur.fetchall()
    }


def calcular_y_guardar_indices(cur: Cursor) -> int:
    """Recalcula el índice de todos los cantones y hace upsert en indice_viabilidad."""
    factor_ambiental = _factor_ambiental(cur)
    factor_inversion = _factor_inversion(cur)
    factor_conectividad = _factor_conectividad(cur)
    factor_seguridad = _factor_seguridad(cur)

    cur.execute("SELECT canton_id FROM cantones")
    canton_ids = [fila["canton_id"] for fila in cur.fetchall()]

    pesos = {
        "ambiental": settings.peso_ambiental,
        "inversion": settings.peso_inversion,
        "conectividad": settings.peso_conectividad,
        "seguridad": settings.peso_seguridad,
    }

    actualizados = 0
    for canton_id in canton_ids:
        fa = factor_ambiental.get(canton_id, 0.0)
        fi = factor_inversion.get(canton_id, 0.0)
        fc = factor_conectividad.get(canton_id, 0.0)
        fs = factor_seguridad.get(canton_id, 0.0)
        total = round(
            fa * pesos["ambiental"]
            + fi * pesos["inversion"]
            + fc * pesos["conectividad"]
            + fs * pesos["seguridad"],
            2,
        )

        cur.execute(
            """
            INSERT INTO indice_viabilidad
                (canton_id, factor_ambiental, factor_inversion, factor_conectividad,
                 factor_seguridad, indice_total, pesos_usados, fecha_calculo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (canton_id) DO UPDATE SET
                factor_ambiental = EXCLUDED.factor_ambiental,
                factor_inversion = EXCLUDED.factor_inversion,
                factor_conectividad = EXCLUDED.factor_conectividad,
                factor_seguridad = EXCLUDED.factor_seguridad,
                indice_total = EXCLUDED.indice_total,
                pesos_usados = EXCLUDED.pesos_usados,
                fecha_calculo = now()
            """,
            (canton_id, fa, fi, fc, fs, total, json.dumps(pesos)),
        )
        actualizados += 1

    return actualizados
