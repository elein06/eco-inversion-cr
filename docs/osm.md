# Fuente OSINT: OpenStreetMap / Overpass API

**Responsable:** Karina (Integrante 3)
**Factor del índice:** Factor de Conectividad (25%)
**Estado:** funcionando de punta a punta — probado contra la base real, no solo en teoría.

## Qué aporta

Puntos de interés relevantes para conectividad e infraestructura por cantón:
centros de acopio (`amenity=recycling`), escuelas (`amenity=school`) y vías
principales/secundarias (`highway=primary|secondary`). La vista
`v_factor_conectividad` (creada por `etl/osm/factor_conectividad.py`)
convierte la cantidad de estos puntos por cantón en el Factor de
Conectividad del Índice de Viabilidad, normalizado 0-100 — igual que hacen
`v_factor_ambiental` (SNIT) y `v_factor_inversion` (SICOP) con sus fuentes.
`backend/app/indice.py` solo lee esa vista, no recalcula nada.

La normalización es min-max sobre los **84 cantones, con y sin POIs** (no
solo los que tienen algo cargado): 100 el que más puntos de interés vigentes
tiene, 0 el que menos o ninguno. Es una decisión del equipo, no un indicador
oficial.

## Archivos de esta carpeta (`etl/osm/`)

| Archivo | Qué hace | Cuándo usarlo |
|---|---|---|
| `sync_osm.py` | El ETL real: consulta Overpass para UN cantón, categoriza y hace upsert en `infraestructura_osm`, respetando la caché de 7 días. Valida cada punto contra el polígono real del cantón (ver más abajo) antes de insertarlo. También acepta `--calcular-factor` (solo o combinado con `--canton`) | `python sync_osm.py --canton "San José" --bbox ...` |
| `cargar_todos_los_cantones.py` | Recorre TODOS los cantones de la tabla `cantones` (calcula el bbox de cada uno con `ST_Extent`, no hay que adivinarlo a mano) y llama a `sincronizar_canton` para cada uno. Con `--calcular-factor`, crea/recrea la vista al terminar | Carga masiva, con pausa entre consultas para no saturar Overpass |
| `factor_conectividad.py` | Crea/recrea la vista `v_factor_conectividad` (Factor de Conectividad + desglose por categoría) | `python sync_osm.py --calcular-factor` (sin `--canton`), o automático con `cargar_todos_los_cantones.py --calcular-factor` |
| `reconciliar_cantones.py` | Migración única: corrige `canton_id` de lo que ya está cargado, cruzando cada punto contra la geometría real de los 84 cantones (sin volver a consultar Overpass) | Una sola vez, para limpiar datos cargados antes del fix de validación espacial — ver sección de abajo |
| `test_overpass.py` | Prueba aislada: consulta Overpass y muestra el resultado en consola, **sin tocar la base de datos** | Para confirmar que la fuente responde antes de cargar nada, o para depurar |

`sync_osm.py` es el módulo central: los otros scripts importan sus funciones
(`consultar_overpass`, `construir_query`, `categorizar`,
`calcular_factor_conectividad`) en vez de duplicar la lógica.

## Dependencia: la tabla `cantones`

**Esta fuente no carga la tabla `cantones`.** La carga el ETL de SNIT
(`etl/snit/`), con los límites oficiales del IGN — ver `docs/snit.md`. Todo
lo de OSM (`sincronizar_canton`, `cargar_todos_los_cantones.py`) busca el
cantón por nombre con `get_canton_id_por_nombre` (en `etl/common/db.py`) y
falla con un mensaje claro si esa tabla está vacía. Antes de correr
cualquier script de OSM: `python etl/snit/sync_snit.py --todas`.

(Antes de que SNIT integrara su ETL, OSM cargaba una versión provisional de
`cantones` desde un GeoJSON público, solo para poder probar el pipeline.
Esa carga provisional ya se eliminó del repo — los códigos de cantón
oficiales del IGN son ahora los únicos que se usan.)

## Endpoint / forma de consumo

- Protocolo: **Overpass QL** sobre la Overpass API pública.
- Instancia principal: `https://overpass-api.de/api/interpreter`
  (configurable con la variable de entorno `OVERPASS_API_URL`).
- Instancia de respaldo (automática si la principal falla): `https://overpass.kumi.systems/api/interpreter`.

```
POST {OVERPASS_API_URL}
Content-Type: application/x-www-form-urlencoded

data=[out:json][timeout:25];
(
  node["amenity"="recycling"]({bbox});
  node["amenity"="school"]({bbox});
  way["highway"~"primary|secondary"]({bbox});
);
out center tags;
```

`{bbox}` tiene el formato `minlat,minlon,maxlat,maxlon`.

- Librerías Python: `requests` (petición HTTP propia), `overpy`
  (`Result.from_json` para convertir la respuesta a objetos Node/Way) y
  `osm2geojson` (conversión a GeoJSON cuando hace falta inspeccionar el
  resultado visualmente).

### Por qué la petición no usa `overpy.Overpass.query()` directamente

`overpy.Overpass.query()` llama internamente a `urllib.request.urlopen` con
el User-Agent por defecto de Python (`Python-urllib/x.y`), y
`overpass-api.de` lo rechaza con `406 Not Acceptable` (piden un User-Agent
que identifique la aplicación que consulta). La función `consultar_overpass`
en `sync_osm.py` hace la petición con `requests` y un User-Agent propio en
su lugar, y además:

- Reintenta con espera progresiva (5s, 10s, 20s) ante `429 Too Many Requests`
  y `504 Gateway Timeout` — comunes cuando se consultan muchos cantones
  seguidos contra la instancia pública.
- Si una instancia agota sus reintentos, prueba con el espejo de respaldo
  antes de rendirse.

## Formato de respuesta (ejemplo real)

```json
{
  "elements": [
    {
      "type": "node",
      "id": 8097748731,
      "lat": 9.9539551,
      "lon": -84.1109118,
      "tags": {
        "amenity": "recycling",
        "name": "Punto Seguro",
        "recycling_type": "container"
      }
    }
  ]
}
```

## Normalización y carga

1. `consultar_overpass()` trae el JSON crudo de Overpass.
2. `overpy.Result.from_json(...)` lo convierte en objetos `Node`/`Way`.
3. `categorizar(tags)` clasifica cada elemento en `centro_acopio`, `escuela`
   o `via_principal` según sus tags (ver `CATEGORIAS_OSM` en `sync_osm.py`).
4. El `canton_id` candidato se resuelve **por nombre de cantón** (parámetro
   `--canton`), una sola vez por corrida, no por cada POI — pero cada POI
   individual se valida por separado contra la geometría real de ese cantón
   antes de aceptarlo (ver paso 5 y la sección de validación espacial).
5. Se hace upsert en `infraestructura_osm` (`ON CONFLICT (osm_id, osm_tipo)`),
   actualizando `fecha_consulta` y `valido_hasta = now() + 7 días` en cada
   corrida, aunque el POI ya existiera — **pero solo si el punto cae
   realmente dentro del polígono del cantón** (ver la sección siguiente). Si
   no, se descarta y se cuenta como "descartado" en la salida del script.
6. Se registra el resultado en `sincronizaciones` (`fuente_id` = OSM), tanto
   en éxito como en error — con el mensaje de la excepción real.

## Validación espacial: por qué el bbox no alcanza

El bbox que se le manda a Overpass es un **rectángulo** (el `ST_Extent` del
cantón, en `cargar_todos_los_cantones.py`). Los cantones de Costa Rica casi
nunca son rectangulares, así que ese rectángulo siempre incluye pedazo de
los cantones vecinos — y en cantones costeros o fronterizos, hasta zonas
fuera de Costa Rica (mar, o el país vecino).

Antes de insertar cada punto, `sincronizar_canton()` valida con
`ST_Contains(cantones.geom, punto)` que caiga de verdad dentro del polígono
del cantón que se está consultando (no solo dentro de su bbox rectangular).
Lo que no pasa esa validación se descarta, no se le asigna al cantón
consultado. El `ON CONFLICT` también actualiza `canton_id` (no solo las
fechas): si un punto ya estaba mal asignado por una corrida vieja, en
cuanto el cantón dueño real lo vuelva a consultar, se corrige solo.

Esto **no corrige datos que ya estaban mal cargados antes de este fix** —
solo protege las cargas nuevas. Para esos, ver `reconciliar_cantones.py`
abajo.

## Factor de Conectividad — vista y endpoint

`etl/osm/factor_conectividad.py` define `v_factor_conectividad`: una vista
normal (no materializada, como `v_factor_inversion` de SICOP) porque es una
cuenta sobre unos cientos de filas sin cruce de geometrías — se calcula en
milisegundos y queda al día sola en cuanto el ETL inserta o vence POIs.

Columnas: `canton_id`, `codigo_ine`, `nombre`, `provincia`,
`pois_centro_acopio`, `pois_escuela`, `pois_via_principal`, `total_pois`,
`factor_conectividad`. El backend la expone en:

- `GET /infraestructura/factor` — los 84 cantones con su desglose
- `GET /infraestructura/factor/{canton_id}` — uno solo
- `GET /infraestructura/resumen` — totales por categoría (no depende de la
  vista, responde aunque no se haya corrido `--calcular-factor`)

Si `v_factor_conectividad` todavía no existe, `/infraestructura/factor`
responde `503` con el comando que falta correr — mismo criterio que
`/inversion/factor` de SICOP.

**Cambio respecto a versiones anteriores del índice:** antes, el cálculo
vivía en `backend/app/indice.py` y el mínimo/máximo de la normalización solo
se tomaba entre los cantones que YA tenían al menos un POI cargado — un
cantón sin ninguno quedaba fuera de esa cuenta y se forzaba a 0 aparte. La
vista usa un `LEFT JOIN` contra los 84 cantones, así que el rango incluye
también a los que no tienen nada. Esto puede mover el número de algún cantón
con poca infraestructura (por ejemplo, de 0 a un valor intermedio) respecto a
antes de este cambio — está documentado en el propio archivo de la vista.

## Migración única: `reconciliar_cantones.py`

Si ya cargaste datos con una versión anterior de `sync_osm.py` (sin la
validación espacial de arriba), esos puntos pueden estar asignados al
cantón equivocado, o incluso a un cantón cuando en realidad caen fuera de
Costa Rica. Este script lo corrige **una sola vez**, sin volver a consultar
Overpass (usa la geometría de los cantones que ya está en la base):

```powershell
cd etl\osm
python reconciliar_cantones.py --solo-contar     # primero, para ver cuánto afectaría
python reconciliar_cantones.py --calcular-factor # aplica el cambio y recrea la vista
```

Hace dos cosas: reasigna cada punto al cantón cuyo polígono realmente lo
contiene (si es distinto del que tenía), y borra los que no caen dentro de
ningún cantón (el bbox los trajo desde fuera de Costa Rica). Después de
correrlo, recalcular el índice: `POST /indice-viabilidad/recalcular`.

## Caché obligatoria

Las instancias públicas de Overpass tienen límites de uso estrictos.
`sincronizar_canton()` revisa primero si ya existen filas en
`infraestructura_osm` con `valido_hasta > now()` para ese cantón; si las hay,
no vuelve a consultar Overpass (a menos que se pase `--forzar`). Esto ya se
probó en la práctica: correr el mismo cantón dos veces seguidas la segunda
vez imprime `Caché vigente ... — no se consulta Overpass` y no hace ninguna
petición nueva.

## Frecuencia de sincronización

Caché de 7 días por cantón (`OSM_CACHE_DIAS`, configurable por variable de
entorno).

## Cómo correrlo

Ver la guía completa (con todos los pasos, desde levantar la base hasta ver
el mapa) en [`docs/guia-equipo-osm.md`](guia-equipo-osm.md). Resumen rápido:

```powershell
cd etl\osm
pip install -r requirements.txt

python test_overpass.py --bbox 9.9,-84.15,9.98,-84.05      # prueba, no toca la base
python sync_osm.py --canton "San José" --bbox 9.9,-84.15,9.98,-84.05
python cargar_todos_los_cantones.py --pausa 3 --calcular-factor  # todos los cantones + vista del factor
```

## Problemas conocidos

Ver la tabla de troubleshooting en
[`docs/guia-equipo-osm.md`](guia-equipo-osm.md#problemas-conocidos-y-como-resolverlos)
(406 de Overpass, 429/504 en cargas masivas, `unaccent` faltante, venvs
cruzadas entre carpetas).
