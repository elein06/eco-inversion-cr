# ETL SNIT — Integrante 1

Consume el **Sistema Nacional de Información Territorial (SNIT)** por servicio
**WFS** y deja tres capas geoespaciales cargadas en PostgreSQL/PostGIS, más el
Factor Ambiental que aporta esta fuente al Índice de Viabilidad.

Fuentes públicas, gratuitas y oficiales del Estado costarricense. Sin
autenticación, sin scraping, sin evadir ningún control.

## Capas que consume

| Capa | Institución | Nodo WFS | Capa (`typeName`) | Features |
|---|---|---|---|---|
| Áreas silvestres protegidas | SINAC | `geos1pne.sirefor.go.cr/wfs` | `PNE:areas_silvestres_protegidas` | 174 |
| Corredores biológicos | SINAC | `geos1pne.sirefor.go.cr/wfs` | `PNE:corredoresbiologicos` | 151 |
| Hidrografía (red de drenaje) | IGN | `geos.snitcr.go.cr/be/IGN_200/wfs` | `IGN_200:reddrenaje_200k` | 6 331 |
| Límites cantonales | IGN | `geos.snitcr.go.cr/be/IGN_5_CO/wfs` | `IGN_5_CO:limitecantonal_5k` | 84 |

Los límites cantonales no estaban en el plan original, pero esta fuente los
carga porque son la **unidad territorial común** contra la que se cruzan las
cuatro fuentes del proyecto. Ningún otro integrante debe llenar esa tabla.

Catálogo oficial: https://www.snitcr.go.cr/ico_servicios_ogc

## Qué hace cada archivo

| Archivo | Rol |
|---|---|
| `sync_snit.py` | **El único que se ejecuta.** Interpreta los argumentos y coordina a los demás |
| `capas.py` | Catálogo: qué capa está en qué nodo y cómo se llama exactamente |
| `descarga_wfs.py` | Habla con el SNIT: `GetCapabilities` y `GetFeature` paginado |
| `respaldo_local.py` | Guarda y lee la copia en `data/`, con procedencia y fecha de consulta |
| `carga_postgis.py` | Inserta las features en `cantones` y `capas_snit` |
| `factor_ambiental.py` | Vista materializada `v_factor_ambiental` con el puntaje por cantón |

Los cinco últimos son módulos: se importan, no se ejecutan directamente.

## Cómo correrlo

Requiere Docker levantado con la base del proyecto (`docker compose up -d db`).

```powershell
pip install -r requirements.txt
```

```powershell
# 1. Explorar: qué capas publica cada nodo (no toca nada)
python sync_snit.py --listar-capas
python sync_snit.py --listar-capas --nodo PNE

# 2. Descargar y revisar los .geojson antes de subirlos (no toca la base)
python sync_snit.py --capa area_protegida --dry-run
python sync_snit.py --todas --dry-run

# 3. Cargar en PostGIS y calcular el Factor Ambiental
python sync_snit.py --todas --calcular-factor

# 4. Recargar sin internet, desde los respaldos de data/
python sync_snit.py --todas --desde-respaldo

# Filtro espacial opcional (minlon,minlat,maxlon,maxlat)
python sync_snit.py --capa area_protegida --bbox=-85.9,10.1,-85.0,11.0 --dry-run
```

Todas las opciones: `python sync_snit.py --help`

**Tiempos.** La descarga completa tarda unos minutos. El cálculo del Factor
Ambiental y su refresco tardan unos 5 minutos cada uno: es el cruce espacial de
84 cantones a escala 1:5mil contra 6 656 geometrías. El script avisa antes de
empezar. Una vez calculada, la vista responde en menos de un segundo.

## Reejecutar no duplica

- `cantones` — upsert por `codigo_ine`: actualiza en vez de insertar de nuevo.
  Importante, porque las otras tres fuentes tienen llaves foráneas a esa tabla.
- `capas_snit` — borra y reinserta por `tipo_capa`, dentro de la misma
  transacción. Se hace así y no con upsert porque el WFS no expone un
  identificador estable por feature: si el SINAC republica la capa, cambian.

## Manejo de errores

- **Nodo que no responde**: 3 reintentos con espera creciente (5s, 10s, 15s).
  Si los tres fallan, lanza `RuntimeError` con la capa y el `startIndex`
  exactos. Nunca falla en silencio.
- **Capa inexistente**: `--capa` solo acepta las cuatro definidas en `capas.py`;
  argparse rechaza cualquier otra antes de salir a la red.
- **Respuesta inesperada**: `raise_for_status()` corta ante cualquier código
  HTTP de error, y el JSON malformado revienta al parsearlo.
- **Trazabilidad**: cada corrida queda registrada en la tabla
  `sincronizaciones` con estado (`exito`, `parcial`, `error`), cantidad de
  registros y mensaje. Los fallos también se registran.
- **Fuente caída**: `--desde-respaldo` recarga desde `data/` sin usar la red.

## Salida

- **`data/*.geojson`** — copia local de cada capa en EPSG:4326, con un bloque
  `metadata` que guarda nodo, capa, fecha de consulta y total de features.
  No se versiona: pesa ~73 MB y está en `.gitignore`.
- **PostgreSQL/PostGIS** — tablas `cantones` y `capas_snit` (ver
  `db/schema.sql`), más la vista materializada `v_factor_ambiental`.

## Configuración

En el `.env` de la raíz, sin secretos — esta fuente no requiere token ni
credenciales:

```
SNIT_WFS_IGN_5_CO_URL, SNIT_WFS_IGN_200_URL, SNIT_WFS_PNE_URL,
SNIT_WFS_VERSION, SNIT_WFS_TIMEOUT, SNIT_WFS_PAGINA
```

## Decisiones técnicas

Documentadas en detalle en [docs/snit.md](../../docs/snit.md). En resumen:

1. **WFS 2.0.0 y no 1.0.0** — la versión 1.0.0 no soporta `startIndex`, y sin
   paginación el nodo del IGN entrega 7 cantones de 84 sin dar error.
2. **Hidrografía a 1:200mil y no a 1:25000** — la capa de 1:25000 tiene
   118 136 features. La de 1:200mil tiene 6 331 y basta para calcular densidad
   de drenaje por cantón.
3. **`psycopg2` y no `geopandas.to_postgis`** — el esquema compartido ya define
   `capas_snit` con `fuente_id`, `tipo_capa` y `atributos` en JSONB;
   `to_postgis` crearía su propia tabla y no encajaría.
4. **Las capas del SINAC no están en `geos.snitcr.go.cr`** — ese nodo tiene el
   WFS deshabilitado. Se publican en `geos1pne.sirefor.go.cr`, que se localizó
   en el catálogo oficial del SNIT.
