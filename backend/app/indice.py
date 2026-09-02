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


def _normalizar_min_max(valores: dict[int, float]) -> dict[int, float]:
    """Escala un dict {canton_id: valor} a 0-100. Si no hay variación, todos quedan en 50."""
    if not valores:
        return {}
    minimo, maximo = min(valores.values()), max(valores.values())
    if maximo == minimo:
        return {canton_id: 50.0 for canton_id in valores}
    return {
        canton_id: round((valor - minimo) / (maximo - minimo) * 100, 2)
        for canton_id, valor in valores.items()
    }


def _factor_ambiental(cur: Cursor) -> dict[int, float]:
    """% del área del cantón que NO se superpone con áreas protegidas / corredores biológicos."""
    cur.execute(
        """
        SELECT
            c.canton_id,
            CASE
                WHEN ST_Area(c.geom) = 0 THEN 100
                ELSE 100 * (
                    1 - COALESCE(
                        ST_Area(ST_Intersection(c.geom, ST_Union(s.geom))) / ST_Area(c.geom),
                        0
                    )
                )
            END AS porcentaje_libre
        FROM cantones c
        LEFT JOIN capas_snit s
            ON s.tipo_capa IN ('area_protegida', 'corredor_biologico')
            AND ST_Intersects(c.geom, s.geom)
        GROUP BY c.canton_id, c.geom
        """
    )
    return {fila["canton_id"]: round(float(fila["porcentaje_libre"]), 2) for fila in cur.fetchall()}


def _factor_inversion(cur: Cursor) -> dict[int, float]:
    """Monto total normalizado de contratos ambientales SICOP por cantón."""
    cur.execute(
        """
        SELECT canton_id, SUM(monto) AS monto_total
        FROM contratos_ambientales
        WHERE canton_id IS NOT NULL
        GROUP BY canton_id
        """
    )
    montos = {fila["canton_id"]: float(fila["monto_total"]) for fila in cur.fetchall()}
    return _normalizar_min_max(montos)


def _factor_conectividad(cur: Cursor) -> dict[int, float]:
    """Densidad normalizada de infraestructura clave (OSM) por cantón."""
    cur.execute(
        """
        SELECT canton_id, COUNT(*) AS total_pois
        FROM infraestructura_osm
        WHERE canton_id IS NOT NULL AND valido_hasta > now()
        GROUP BY canton_id
        """
    )
    conteos = {fila["canton_id"]: float(fila["total_pois"]) for fila in cur.fetchall()}
    return _normalizar_min_max(conteos)


def _factor_seguridad(cur: Cursor) -> dict[int, float]:
    """Inverso de la tasa de incidencia delictiva (OIJ), normalizada por cantón."""
    cur.execute(
        """
        SELECT
            c.canton_id,
            COALESCE(SUM(e.cantidad), 0) AS total_delitos,
            c.poblacion
        FROM cantones c
        LEFT JOIN estadisticas_seguridad e ON e.canton_id = c.canton_id
        GROUP BY c.canton_id, c.poblacion
        """
    )
    tasas: dict[int, float] = {}
    for fila in cur.fetchall():
        if fila["poblacion"]:
            tasas[fila["canton_id"]] = fila["total_delitos"] / fila["poblacion"] * 10_000
        else:
            tasas[fila["canton_id"]] = float(fila["total_delitos"])

    normalizado = _normalizar_min_max(tasas)
    # Invertir: a menor tasa de criminalidad, mayor puntaje de seguridad.
    return {canton_id: round(100 - score, 2) for canton_id, score in normalizado.items()}


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
