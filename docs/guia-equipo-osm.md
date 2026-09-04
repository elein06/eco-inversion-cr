# Guía para el equipo — cómo funciona OSM y cómo verlo

Este documento es para que cualquiera del equipo pueda levantar el proyecto
en su máquina y ver los datos de OpenStreetMap/Overpass ya funcionando
(cantones + infraestructura + el Índice de Viabilidad calculándose con
datos reales de esta fuente), sin tener que adivinar nada.

## Paso a paso

### 0. Requisitos

- Docker Desktop instalado y abierto.

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

Si ya tenías el contenedor de Postgres levantado **desde antes** de este
PR (el volumen ya existía), el fix de `unaccent` en `schema.sql` no se va a
aplicar solo, porque ese script de inicialización solo corre la primera vez
que se crea la base. Corré esto una vez a mano:

```powershell
docker exec -it eco-inversion-db psql -U eco_inversion -d eco_inversion_cr -c "CREATE EXTENSION IF NOT EXISTS unaccent;"
```

(Si preferís empezar de cero: `docker compose down -v` borra el volumen y
la próxima vez que levantes `db` corre `schema.sql` completo, ya con el fix
incluido — pero perdés cualquier dato que ya tuvieras cargado.)

### 4. Cargar la tabla `cantones` (una sola vez, la necesitan las 4 fuentes)

Descargá manualmente este archivo 

- https://github.com/maufonsecasdfg/costa-rica-geojson/blob/main/costaricacantones.geojson

Guardalo como `db/cantones_cr.geojson` (si ya viene incluido en /db, te
podés saltar la descarga).

```powershell
cd etl\common
python -m venv venv
venv\Scripts\activate
pip install -r ..\osm\requirements.txt
python load_cantones.py --geojson ..\..\db\cantones_cr.geojson
```

Vas a ver algo como `81-84 cantones insertados`. Los códigos `codigo_ine`
que genera son **provisionales** (no son el código oficial INEC/DTA) — ver
`docs/cantones.md` si hace falta más detalle.

### 5. Cargar infraestructura de OSM (opcional si solo querés ver, no repetir la carga)

```powershell
docker exec -i eco-inversion-db psql -U eco_inversion -d eco_inversion_cr < etl\osm\seed_osm.sql
```

Si no hay dump y querés los datos reales de Overpass vos mismo:

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




## Problemas conocidos y cómo resolverlos

| Síntoma | Causa | Solución |
|---|---|---|
| `function unaccent(text) does not exist` | Volumen de Postgres creado antes del fix del schema | Paso 3, comando de `CREATE EXTENSION` a mano |
| `406 Not Acceptable` de Overpass | User-Agent por defecto de `urllib`/`overpy` | Ya corregido en `sync_osm.py`; si aparece en OTRA fuente que también use `requests`/`urllib`, es probablemente el mismo tipo de bloqueo |
| `429 Too Many Requests` / `504 Gateway Timeout` de Overpass | Instancia pública saturada, sobre todo en cargas masivas | Ya tiene reintentos con espera progresiva y espejo de respaldo; si persiste, correr ese cantón suelto más tarde con `--forzar` |
| El mapa muestra datos de prueba (mock) en vez de reales | El backend no está corriendo o no tiene datos | Revisar que `uvicorn` esté arriba y que se haya llamado a `/recalcular` |
| `ModuleNotFoundError` para `osm2geojson`, `overpy`, etc. | La venv activada no es la que tiene esas dependencias instaladas (fácil de confundir si tenés varias venvs por carpeta) | Confirmar con `where python` cuál venv está activa, y correr `pip install -r requirements.txt` en esa misma |
