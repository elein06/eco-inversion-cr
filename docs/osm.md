# Fuente OSINT: OpenStreetMap / Overpass API

**Responsable:** Karina (Integrante 3)
**Factor del índice:** Factor de Conectividad (25%)
**Estado:** funcionando de punta a punta — probado contra la base real, no solo en teoría.

## Qué aporta

Puntos de interés relevantes para conectividad e infraestructura por cantón:
centros de acopio (`amenity=recycling`), escuelas (`amenity=school`) y vías
principales/secundarias (`highway=primary|secondary`). El backend usa la
cantidad de estos puntos por cantón, normalizada 0-100, como Factor de
Conectividad del Índice de Viabilidad (ver `backend/app/indice.py`).

## Archivos de esta carpeta (`etl/osm/`)

| Archivo | Qué hace | Cuándo usarlo |
|---|---|---|
| `sync_osm.py` | El ETL real: consulta Overpass para UN cantón, categoriza y hace upsert en `infraestructura_osm`, respetando la caché de 7 días | `python sync_osm.py --canton "San José" --bbox ...` |
| `cargar_todos_los_cantones.py` | Recorre TODOS los cantones de la tabla `cantones` (calcula el bbox de cada uno con `ST_Extent`, no hay que adivinarlo a mano) y llama a `sincronizar_canton` para cada uno | Carga masiva, con pausa entre consultas para no saturar Overpass |
| `test_overpass.py` | Prueba aislada: consulta Overpass y muestra el resultado en consola, **sin tocar la base de datos** | Para confirmar que la fuente responde antes de cargar nada, o para depurar |

`sync_osm.py` es el módulo central: los otros dos scripts importan sus
funciones (`consultar_overpass`, `construir_query`, `categorizar`) en vez de
duplicar la lógica.

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
4. El `canton_id` se resuelve **por nombre de cantón** (parámetro `--canton`),
   no por intersección espacial — se busca una sola vez por corrida, no por
   cada POI.
5. Se hace upsert en `infraestructura_osm` (`ON CONFLICT (osm_id, osm_tipo)`),
   actualizando `fecha_consulta` y `valido_hasta = now() + 7 días` en cada
   corrida, aunque el POI ya existiera.
6. Se registra el resultado en `sincronizaciones` (`fuente_id` = OSM), tanto
   en éxito como en error — con el mensaje de la excepción real.

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
python cargar_todos_los_cantones.py --pausa 3                # todos los cantones
```

## Problemas conocidos

Ver la tabla de troubleshooting en
[`docs/guia-equipo-osm.md`](guia-equipo-osm.md#problemas-conocidos-y-como-resolverlos)
(406 de Overpass, 429/504 en cargas masivas, `unaccent` faltante, venvs
cruzadas entre carpetas).
