# Eco-Inversión Costa Rica

Plataforma tipo mapa interactivo para ONGs, emprendedores sociales e inversionistas que buscan el cantón más adecuado para proyectos de impacto (ecoturismo, reciclaje, agricultura sostenible). El sistema cruza cuatro fuentes OSINT de Costa Rica y calcula, por cantón, un **Índice de Viabilidad** (0-100).

Trabajo de Investigación 2 — Seguridad Informática.

## Fuentes OSINT y responsables

| Fuente | Aporta | Factor del índice | Responsable | Detalle |
|---|---|---|---|---|
| **SNIT** (WFS) | Áreas protegidas, corredores biológicos, hidrografía | Ambiental (25%) | Integrante 1 | [docs/snit.md](docs/snit.md) |
| **SICOP** (API de datos abiertos) | Contratos municipales ambientales | Inversión (25%) | Integrante 2 | [docs/sicop.md](docs/sicop.md) |
| **OpenStreetMap / Overpass** | Infraestructura y conectividad | Conectividad (25%) | Integrante 3 | [docs/osm.md](docs/osm.md) |
| **Poder Judicial / OIJ** (CKAN) | Estadísticas policiales agregadas | Seguridad (25%) | Integrante 4 | [docs/oij.md](docs/oij.md) |

La fuente OIJ reemplaza a la fuente económica original del BCCR: evita el trámite de token del servicio SOAP y añade una dimensión de seguridad directamente relevante para el curso.

Los pesos del índice (25% cada uno) son una decisión del equipo, no un estándar oficial — se documentan en [backend/app/config.py](backend/app/config.py) y se devuelven en cada respuesta de `/indice-viabilidad`.

**Advertencia ética:** las estadísticas del OIJ son agregadas por cantón. El sistema nunca insinúa que un cantón "peligroso" implica algo sobre sus habitantes, y su relación con el índice de viabilidad es una correlación definida por el equipo, no una causalidad. Ver [docs/oij.md](docs/oij.md).

Plan completo del proyecto (cronograma, riesgos, checklist de rúbrica): [docs/PLAN.md](docs/PLAN.md).

## Arquitectura

```
Frontend (React + Leaflet)  →  Backend propio (FastAPI)  →  PostgreSQL + PostGIS
                                       ↑
                          ETL por fuente (SNIT, SICOP, OSM, OIJ)
```

El frontend **nunca** consulta SNIT, SICOP, OSM ni el Poder Judicial directamente — solo habla con la API propia del backend, que expone datos ya normalizados:

- `GET /zonas` — cantones con geometría (GeoJSON)
- `GET /contratos-ambientales` — contratos SICOP clasificados
- `GET /infraestructura` — POIs de OSM (con caché de 7 días)
- `GET /seguridad` — estadísticas OIJ agregadas por cantón
- `GET /indice-viabilidad` / `POST /indice-viabilidad/recalcular` — índice calculado

## Estructura del repositorio

```
/etl/snit          → ETL de Integrante 1 (WFS → GeoJSON → PostGIS)
/etl/sicop         → ETL de Integrante 2 (API SICOP → clasificación → PostgreSQL)
/etl/osm           → ETL de Integrante 3 (Overpass → GeoJSON → caché)
/etl/oij           → ETL de Integrante 4 (CKAN → estadísticas → carga)
/etl/common        → conexión a BD y registro de sincronizaciones, compartido
/backend           → API propia en FastAPI + cálculo del índice
/frontend          → mapa interactivo (React + Leaflet) + panel de resultados
/db/schema.sql     → esquema completo de PostgreSQL + PostGIS
/docs              → un archivo por fuente + plan de proyecto
.env.example       → variables de entorno documentadas, sin secretos reales
docker-compose.yml → Postgres+PostGIS y backend para desarrollo local
```

## Cómo correr el proyecto

### 1. Base de datos (Docker Compose)

```bash
cp .env.example .env
docker compose up -d db
```

Esto levanta Postgres+PostGIS y carga automáticamente `db/schema.sql` (extensión PostGIS, tablas, datos semilla de `fuentes`).

Si el puerto 5432 ya lo ocupa un Postgres instalado en la máquina, cambiar `POSTGRES_PORT` en el `.env`: solo afecta al puerto del host, porque dentro de Docker el contenedor sigue en 5432 y el backend de compose le habla por el nombre `db`.

Si la tabla `cantones` todavía no está cargada (por ejemplo, antes de correr el ETL del SNIT), hay que cargarla porque es el eje territorial contra el que se cruzan las cuatro fuentes:

```bash
cd etl/common && pip install psycopg2-binary python-dotenv
python load_cantones.py --geojson ../../db/cantones_cr.geojson
```

### 1-bis. Alternativa: un PostgreSQL ya instalado en la máquina

Se puede usar en lugar de Docker, siempre que tenga **PostGIS** (no viene con
el instalador de PostgreSQL: se agrega desde Stack Builder, en *Spatial
Extensions*). Sin PostGIS, `db/schema.sql` falla en su primera línea.

```bash
# 1. Crear rol, base y extensiones (pide la contraseña del superusuario postgres)
psql -U postgres -d postgres -f db/setup_local.sql

# 2. Cargar el esquema CON EL ROL DE LA APLICACIÓN, no como postgres,
#    para que las tablas queden con el dueño correcto
psql -U eco_inversion -d eco_inversion_cr -f db/schema.sql
```

Si el paso 2 ya se corrió como `postgres`, las tablas quedan con ese dueño y
los ETL fallan con `permission denied for table cantones`. Se arregla sin
rehacer la base:

```bash
psql -U postgres -d eco_inversion_cr -f db/grant_local.sql
```

`db/setup_local.sql` deja el rol `eco_inversion` con la contraseña de ejemplo
`changeme`, que es la que trae `.env.example`. Si se cambia, hay que cambiarla
también en `DATABASE_URL`.

### 2. Backend (FastAPI)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API disponible en `http://localhost:8000`, documentación interactiva en `http://localhost:8000/docs`.

También se puede levantar dentro de Docker, que es lo más parecido a como va a
correr en la demo:

```bash
docker compose up -d --build backend
```

En ese caso el backend no usa `DATABASE_URL` del `.env`: `docker-compose.yml`
le pasa una propia que apunta al contenedor `db` por nombre de servicio. Para
desarrollar conviene el `uvicorn --reload` de arriba, porque recarga al
guardar; el contenedor hay que reconstruirlo.

### 3. ETL por fuente

Cada integrante corre su propio script desde `/etl/<fuente>`, apuntando al mismo `DATABASE_URL`. Ejemplos:

> **Orden importante:** el ETL del SNIT va primero. Es el que llena la tabla
> `cantones`, la unidad territorial contra la que se cruzan las otras tres
> fuentes. Nadie más debe cargar esa tabla.

```bash
# 1. SNIT — carga cantones + las 3 capas ambientales y calcula el Factor Ambiental
cd etl/snit    && pip install -r requirements.txt && python sync_snit.py --todas --calcular-factor
cd etl/sicop   && pip install -r requirements.txt && python sync_sicop.py --solicitar --todos --correo yo@ejemplo.com
#    SICOP manda un codigo por correo; se confirma y el script baja, clasifica y carga:
#    python sync_sicop.py --confirmar --codigo <codigo del correo>
#    python sync_sicop.py --cargar --calcular-factor
cd etl/osm     && pip install -r requirements.txt && python sync_osm.py --canton "San José" --bbox 9.9,-84.12,9.95,-84.06
cd etl/oij     && pip install -r requirements.txt && python sync_oij.py --archivo reportes/estadisticas_2024.csv --anio 2024
```

Guías paso a paso para levantar cada fuente desde cero, pensadas para el resto
del equipo: [docs/guia-equipo-sicop.md](docs/guia-equipo-sicop.md) ·
[docs/guia-equipo-osm.md](docs/guia-equipo-osm.md).

Cada script trae su propia ayuda con todas las opciones disponibles:

```bash
python sync_snit.py --help
```

Detalle de cada fuente —endpoints, formatos, tiempos esperados y decisiones
técnicas— en su archivo de `/docs`.

Después de cargar datos nuevos, recalcular el índice:

```bash
curl -X POST http://localhost:8000/indice-viabilidad/recalcular
```

### 4. Frontend (React + Vite + Leaflet)

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Disponible en `http://localhost:5173`. Si la API del backend todavía no tiene datos (o no está corriendo), el frontend cae automáticamente a datos de prueba (`src/mock.ts`) y lo indica con un banner, para no bloquear el desarrollo visual mientras el resto del equipo carga las fuentes reales.

## Variables de entorno

Ver [.env.example](.env.example) (raíz, usado por Docker Compose/backend/ETL) y [frontend/.env.example](frontend/.env.example) (usado por Vite). Nunca commitear un archivo `.env` real.

## Estado del proyecto

Ver el cronograma de dos semanas y el checklist de rúbrica en [docs/PLAN.md](docs/PLAN.md).
