"""
Reconciliación espacial única — Integrante 3 — OSM/Overpass

`sync_osm.py` consulta Overpass con un bbox RECTANGULAR (el `ST_Extent` del
cantón, calculado por `cargar_todos_los_cantones.py`). Como los cantones de
Costa Rica casi nunca son rectángulos, ese bbox siempre agarra pedazo de los
cantones vecinos — y en cantones costeros o fronterizos, hasta zonas fuera
de Costa Rica (mar, o el país vecino). Antes de que `sincronizar_canton()`
validara cada punto contra el polígono real (ver el `WHERE ST_Contains(...)`
en `sync_osm.py`), todo lo que traía esa consulta se insertaba con el
`canton_id` del cantón que se estaba consultando, sin importar dónde cayera
el punto de verdad.

Ese fix de `sync_osm.py` solo protege las cargas NUEVAS. Este script corrige
de una sola vez los datos que ya estaban en la base desde antes del fix —
sin volver a consultar Overpass, porque ya se tiene todo lo necesario en la
propia base: la geometría real de los 84 cantones (cargada por el ETL del
SNIT) y la posición real de cada punto ya guardada en `infraestructura_osm`.

Hace dos cosas, ambas basadas en `ST_Contains(cantones.geom, punto)`:

  1. REASIGNA cada punto al cantón cuyo polígono realmente lo contiene, si
     es distinto del que tenía (ej.: un punto cargado como "Nicoya" que en
     realidad cae dentro de Santa Cruz).
  2. BORRA los puntos que no caen dentro de NINGÚN cantón — el bbox los
     trajo desde fuera de Costa Rica (otro país, el mar) y no le pertenecen
     a nadie; no tiene sentido dejarlos con un canton_id inventado.

Uso:
    python reconciliar_cantones.py                    # corrige y borra
    python reconciliar_cantones.py --solo-contar       # no toca nada, solo informa cuánto afectaría
    python reconciliar_cantones.py --calcular-factor   # además recrea v_factor_conectividad al terminar
"""
import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

from db import get_connection, registrar_sincronizacion  # noqa: E402
from factor_conectividad import calcular_factor_conectividad  # noqa: E402

_SQL_CONTAR_REASIGNAR = """
    SELECT count(*) FROM infraestructura_osm o
    JOIN cantones c ON ST_Contains(c.geom, o.geom)
    WHERE o.canton_id IS DISTINCT FROM c.canton_id
"""

_SQL_CONTAR_BORRAR = """
    SELECT count(*) FROM infraestructura_osm o
    WHERE NOT EXISTS (SELECT 1 FROM cantones c WHERE ST_Contains(c.geom, o.geom))
"""

_SQL_REASIGNAR = """
    UPDATE infraestructura_osm o
    SET canton_id = c.canton_id
    FROM cantones c
    WHERE ST_Contains(c.geom, o.geom)
      AND o.canton_id IS DISTINCT FROM c.canton_id
"""

_SQL_BORRAR = """
    DELETE FROM infraestructura_osm o
    WHERE NOT EXISTS (SELECT 1 FROM cantones c WHERE ST_Contains(c.geom, o.geom))
"""


def contar_afectados(conn) -> tuple[int, int]:
    with conn.cursor() as cur:
        cur.execute(_SQL_CONTAR_REASIGNAR)
        a_reasignar = cur.fetchone()[0]
        cur.execute(_SQL_CONTAR_BORRAR)
        a_borrar = cur.fetchone()[0]
    return a_reasignar, a_borrar


def reconciliar(conn) -> tuple[int, int]:
    with conn.cursor() as cur:
        # Primero reasignar, después borrar: un punto que cae fuera de todo
        # cantón no se toca en el UPDATE (ST_Contains nunca da true para él),
        # así que el orden entre los dos pasos no cambia el resultado — pero
        # reasignar primero dejar métricas más claras en pantalla.
        cur.execute(_SQL_REASIGNAR)
        reasignados = cur.rowcount
        cur.execute(_SQL_BORRAR)
        borrados = cur.rowcount
    return reasignados, borrados


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Corrige canton_id de infraestructura_osm contra la geometría real de los cantones (una sola vez, sin Overpass)"
    )
    parser.add_argument(
        "--solo-contar",
        action="store_true",
        help="No modifica nada — solo muestra cuántas filas se reasignarían/borrarían",
    )
    parser.add_argument(
        "--calcular-factor",
        action="store_true",
        help="Recrea v_factor_conectividad al terminar (para ver el ranking ya corregido)",
    )
    args = parser.parse_args()

    with get_connection() as conn:
        if args.solo_contar:
            a_reasignar, a_borrar = contar_afectados(conn)
            print(f"Se reasignarían {a_reasignar} punto(s) a su cantón real.")
            print(
                f"Se borrarían {a_borrar} punto(s) que no caen dentro de ningún cantón "
                "(fuera de Costa Rica, o zona de mar que el bbox alcanzó a agarrar)."
            )
            print("(No se modificó nada — corré sin --solo-contar para aplicar el cambio.)")
            return

        reasignados, borrados = reconciliar(conn)
        registrar_sincronizacion(
            conn,
            fuente_codigo="OSM",
            estado="exito",
            registros_procesados=reasignados + borrados,
            mensaje=f"Reconciliación espacial única: {reasignados} reasignados, {borrados} borrados",
        )
        print(f"OK: {reasignados} punto(s) reasignados a su cantón real, {borrados} punto(s) borrados.")

    if args.calcular_factor:
        calcular_factor_conectividad()
    else:
        print("Corré 'python sync_osm.py --calcular-factor' para ver el ranking ya corregido "
              "y después 'POST /indice-viabilidad/recalcular' para que se refleje en el mapa.")


if __name__ == "__main__":
    main()
