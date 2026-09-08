# Guía para el equipo — qué hizo Integrante 3 (OSM) y cómo verlo

Este documento es para que cualquiera del equipo pueda levantar el proyecto
en su máquina y ver los datos de OpenStreetMap/Overpass ya funcionando
(infraestructura + el Índice de Viabilidad calculándose con datos reales de
esta fuente), sin tener que adivinar nada.

## Resumen de lo que se hizo

- Se probó y arregló el ETL de OSM (`etl/osm/sync_osm.py`): la consulta a
  Overpass fallaba con `406 Not Acceptable` porque `overpy` usa el
  User-Agent por defecto de Python, que Overpass rechaza. Ahora se hace la
  petición con `requests` y un User-Agent propio, con reintentos ante
  `429`/`504` y un espejo de respaldo si la instancia principal se satura.
- Se corrigió un bug en `db/schema.sql`: faltaba `CREATE EXTENSION
  unaccent`, que usa `etl/common/db.py` para buscar cantones por nombre.
- Se agregaron scripts de prueba (`etl/osm/test_overpass.py`, que no toca la
  base de datos) y de carga masiva (`etl/osm/cargar_todos_los_cantones.py`,
  que carga OSM para todos los cantones automáticamente, calculando el bbox
  de cada uno desde su geometría real en vez de tenerlo que adivinar a mano).
- La tabla compartida `cantones` la carga el ETL de SNIT (`etl/snit/`), con
  los códigos oficiales del IGN. OSM depende de que esa tabla ya tenga datos
  antes de correr cualquiera de sus scripts.

## Paso a paso

### 0. Requisitos

- Docker Desktop instalado y abierto.
- Python 3.10+ y Node.js instalados.
- Traer la rama/PR correspondiente o el merge a `main` una vez aprobado.

### 1. Traer el código

```powershell
git pull origin main
```

### 2. Variables de entorno (una sola vez)

```powershell
cd C:\ruta\a\eco-inversion-cr
copy .env.example .env
cd frontend
copy .env.example .env
cd ..
```

### 3. Levantar la base de datos

```powershell
docker compose up -d db
docker ps        # confirmar que "eco-inversion-db" está corriendo
```

Si ya tenías el contenedor de Postgres levantado **desde antes** de que se
agregara `unaccent` a `schema.sql`, ese fix no se aplica solo (el script de
inicialización solo corre la primera vez que se crea el volumen). Corré esto
una vez a mano:

```powershell
docker exec -it eco-inversion-db psql -U eco_inversion -d eco_inversion_cr -c "CREATE EXTENSION IF NOT EXISTS unaccent;"
```

### 4. Cargar `cantones` + capas SNIT (una sola vez, la necesitan las 4 fuentes)

```powershell
cd etl\snit
pip install -r requirements.txt
python sync_snit.py --todas --calcular-factor
```

Esto carga los 84 cantones oficiales del IGN y las capas ambientales del
SNIT (áreas protegidas, corredores biológicos). Ver `docs/snit.md` para el
detalle de este ETL.

**Si tu base ya tenía cantones cargados con códigos distintos** (por
ejemplo de una versión anterior de este proyecto que usaba un GeoJSON
provisional), hay que vaciar y recargar todo junto, porque los `canton_id`
cambian:

```powershell
docker exec -it eco-inversion-db psql -U eco_inversion -d eco_inversion_cr -c "TRUNCATE cantones, capas_snit, infraestructura_osm, contratos_ambientales, estadisticas_seguridad, indice_viabilidad RESTART IDENTITY CASCADE;"
```

y después repetir el paso 4 y seguir con el paso 5.

### 5. Cargar infraestructura de OSM

```powershell
cd etl\osm
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

python test_overpass.py --bbox 9.9,-84.15,9.98,-84.05      # prueba rápida, sin tocar la base
python cargar_todos_los_cantones.py --pausa 3               # carga real, tarda varios minutos
```

### 6. Levantar el backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Confirmá en http://localhost:8000/docs que responde.

### 7. Calcular el índice

```powershell
curl.exe -X POST http://localhost:8000/indice-viabilidad/recalcular
```

Hay que repetir esto cada vez que se cargan datos nuevos de cualquier
fuente — el índice no se recalcula solo.

### 8. Levantar el frontend

```powershell
cd frontend
npm install
npm run dev
```

Abrir http://localhost:5173. Debería verse el mapa de Costa Rica con todos
los cantones, coloreados según `indice_total`.

## Cómo confirmar que los datos de OSM están ahí

```powershell
docker exec -it eco-inversion-db psql -U eco_inversion -d eco_inversion_cr -c "SELECT count(*) FROM infraestructura_osm;"
docker exec -it eco-inversion-db psql -U eco_inversion -d eco_inversion_cr -c "SELECT categoria, count(*) FROM infraestructura_osm GROUP BY categoria;"
docker exec -it eco-inversion-db psql -U eco_inversion -d eco_inversion_cr -c "SELECT * FROM sincronizaciones WHERE fuente_id = (SELECT fuente_id FROM fuentes WHERE codigo='OSM') ORDER BY fecha_ejecucion DESC LIMIT 5;"
```

## Por qué el índice se ve casi igual en todos los cantones (mientras faltan fuentes)

Con solo SNIT y OSM cargados, el Factor de Inversión (SICOP) da 0 parejo y
el Factor de Seguridad (OIJ) cae en su caso "sin datos" (50 parejo para
todos) — el Factor Ambiental (SNIT) y el de Conectividad (OSM) sí varían de
verdad entre cantones. Esto es esperado, no un bug — a medida que cada quien
cargue su fuente, el mapa va a diferenciar más zonas. Después de cada carga
nueva, no te olvidés del paso 7 (`/recalcular`).

## Problemas conocidos y cómo resolverlos

| Síntoma | Causa | Solución |
|---|---|---|
| `function unaccent(text) does not exist` | Volumen de Postgres creado antes del fix del schema | Paso 3, comando de `CREATE EXTENSION` a mano |
| `No hay cantones en la tabla cantones` al correr algo de OSM | Falta correr el ETL de SNIT primero | Paso 4 |
| Cantones duplicados / `canton_id` que no coinciden entre fuentes | Se cargó `cantones` con dos fuentes de códigos distintas (por ejemplo un GeoJSON provisional y después el WFS oficial del IGN) | `TRUNCATE ... CASCADE` (paso 4) y recargar todo en orden: SNIT primero, después el resto |
| `406 Not Acceptable` de Overpass | User-Agent por defecto de `urllib`/`overpy` | Ya corregido en `sync_osm.py`; si aparece en OTRA fuente que también use `requests`/`urllib`, es probablemente el mismo tipo de bloqueo |
| `429 Too Many Requests` / `504 Gateway Timeout` de Overpass | Instancia pública saturada, sobre todo en cargas masivas | Ya tiene reintentos con espera progresiva y espejo de respaldo; si persiste, correr ese cantón suelto más tarde con `--forzar` |
| El mapa muestra datos de prueba (mock) en vez de reales | El backend no está corriendo o no tiene datos | Revisar que `uvicorn` esté arriba y que se haya llamado a `/recalcular` |
| `ModuleNotFoundError` para `osm2geojson`, `overpy`, etc. | La venv activada no es la que tiene esas dependencias instaladas (fácil de confundir si tenés varias venvs por carpeta) | Confirmar con `where python` cuál venv está activa, y correr `pip install -r requirements.txt` en esa misma |
| `fatal: Unable to create '.git/index.lock': File exists` | Quedó un lock de una corrida anterior de git interrumpida | Borrar `.git/index.lock` a mano (con git cerrado en cualquier otra ventana/IDE) |
