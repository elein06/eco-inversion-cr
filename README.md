# Eco-Inversión Costa Rica

Plataforma tipo mapa interactivo para ONGs, emprendedores sociales e inversionistas que buscan el cantón más adecuado para proyectos de impacto (ecoturismo, reciclaje, agricultura sostenible). El sistema cruza cuatro fuentes OSINT de Costa Rica y calcula, por cantón, un **Índice de Viabilidad** (0-100).

Trabajo de Investigación 2 — Seguridad Informática.

## Fuentes OSINT y responsables

| Fuente | Aporta | Factor del índice | Responsable | Detalle |
|---|---|---|---|---|
| **SNIT** (WFS) | Áreas protegidas, corredores biológicos, hidrografía | Ambiental (25%) | Integrante 1 | [docs/snit.md](docs/snit.md) |
| **SICOP** (datos abiertos) | Contratos municipales ambientales | Inversión (25%) | Integrante 2 | [docs/sicop.md](docs/sicop.md) |
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
/etl/sicop         → ETL de Integrante 2 (descarga + clasificación + carga)
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

Esto levanta Postgres+PostGIS en `localhost:5432` y carga automáticamente `db/schema.sql` (extensión PostGIS, tablas, datos semilla de `fuentes`).

Sin Docker, se puede usar cualquier Postgres con PostGIS instalado y correr:

```bash
psql "$DATABASE_URL" -f db/schema.sql
```

### 2. Backend (FastAPI)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API disponible en `http://localhost:8000`, documentación interactiva en `http://localhost:8000/docs`.

### 3. ETL por fuente

Cada integrante corre su propio script desde `/etl/<fuente>`, apuntando al mismo `DATABASE_URL`. Ejemplos:

> **Orden importante:** el ETL del SNIT va primero. Es el que llena la tabla
> `cantones`, la unidad territorial contra la que se cruzan las otras tres
> fuentes. Nadie más debe cargar esa tabla.

```bash
# 1. SNIT — carga cantones + las 3 capas ambientales y calcula el Factor Ambiental
cd etl/snit    && pip install -r requirements.txt && python sync_snit.py --todas --calcular-factor
cd etl/sicop   && pip install -r requirements.txt && python sync_sicop.py --archivo reportes/contratos.xlsx
cd etl/osm     && pip install -r requirements.txt && python sync_osm.py --canton "San José" --bbox 9.9,-84.12,9.95,-84.06
cd etl/oij     && pip install -r requirements.txt && python sync_oij.py --archivo reportes/estadisticas_2024.csv --anio 2024
```

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
