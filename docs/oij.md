# Fuente OSINT: Poder Judicial / OIJ — Estadísticas Policiales

**Responsable:** Integrante 4
**Factor del índice:** Factor de Seguridad (25%)
**Nota:** reemplaza a la fuente original del BCCR (evita el trámite de token del servicio SOAP y añade una dimensión de seguridad alineada con el curso).

## Qué aporta

Incidentes policiales por cantón, tipo de delito, año, agregados por el propio ETL del proyecto (el recurso original es a nivel de incidente, ver abajo), usados como proxy (inverso) de seguridad para el índice de viabilidad.

## Endpoint / forma de consumo (verificada)

Portal de Datos Abiertos del Poder Judicial, construido sobre **CKAN**, dataset `estadisticas-policiales`. No requiere token.

- Página del dataset: `https://datosabiertospj.poder-judicial.go.cr/dataset/estadisticas-policiales`
- Descarga directa por año, ej.:
  ```
  https://pjcrdatosabiertos.blob.core.windows.net/datosabiertos/PJCROD_POLICIALES_V1/PJCROD_POLICIALES_V1-2025.csv
  ```
- También hay XLSX, XML y RDF por año, y un `--resource-id` de CKAN por recurso — no se confirmó si el datastore de CKAN está activo para este dataset, así que **la vía verificada y recomendada es la descarga directa del CSV**, no la API `datastore_search`.

## Hallazgos del formato real (importante — difiere de lo que se asumió al planear el proyecto)

Al inspeccionar el CSV real se encontró que **no es un archivo pre-agregado** como se pensó originalmente ("Cantón, Delito, Cantidad, Año"), sino un registro por incidente, sin encabezado, con 11 columnas posicionales:

| # | Columna | Ejemplo |
|---|---|---|
| 0 | tipo_delito | ASALTO, HOMICIDIO, ROBO, HURTO, ROBO DE VEHICULO, TACHA DE VEHICULO |
| 1 | subtipo_delito / modalidad | CANDADO CHINO, ARREBATO |
| 2 | fecha_hecho (YYYY-MM-DD) | 2025-01-01 |
| 3 | tipo_víctima | PERSONA, VIVIENDA, VEHÍCULO |
| 4 | clasificación de víctima | TURISTA/EXTRANJERO [PERSONA] |
| 5 | grupo etario | Mayor de edad, Desconocido |
| 6 | (columna reservada, vacía) | — |
| 7 | nacionalidad | COSTA RICA, NICARAGUA |
| 8 | provincia | SAN JOSE |
| 9 | cantón | CURRIDABAT |
| 10 | distrito | TIRRASES |

Además, el archivo viene en **codificación latin-1 / cp1252, no UTF-8** (nombres con tilde o ñ se corrompen si se lee como UTF-8 — ej. "CAÑAS" → "CA�AS").

Por esto, `etl/oij/sync_oij.py` no solo limpia el archivo: **agrupa y cuenta** filas por cantón + tipo_delito + año antes de insertar en `estadisticas_seguridad`. Esa agregación es la transformación real que exige el enunciado del curso (no basta con copiar el archivo tal cual).

## Normalización y carga (flujo actual del script)

1. Leer el CSV sin encabezado, columnas posicionales, probando encodings `latin-1` → `cp1252` → `utf-8` en ese orden.
2. Limpiar espacios y pasar a mayúsculas cantón/provincia/tipo_delito; extraer el año de `fecha_hecho`.
3. Descartar filas sin cantón, delito o fecha válida.
4. Agrupar por (cantón, tipo_delito, año) y contar incidentes → columna `cantidad`.
5. Buscar `canton_id` en la tabla `cantones` por nombre (insensible a tildes/mayúsculas). Los cantones sin match se reportan al final y se omiten — no se pierde la corrida completa por un nombre no reconocido.
6. `INSERT ... ON CONFLICT (canton_id, tipo_delito, anio) DO UPDATE` en `estadisticas_seguridad`, para poder re-ejecutar el script sin duplicar.
7. Registrar la corrida en `sincronizaciones` (`fuente_id` = OIJ), incluso si falla.

## Bloqueo detectado: `cantones` está vacía

Ningún script del repositorio puebla todavía la tabla `cantones` (el ETL de SNIT solo carga `capas_snit`, no las 84 filas de `cantones` con su geometría). Como `estadisticas_seguridad.canton_id` depende de esa tabla, **ninguna fuente puede cargar datos reales hasta que exista ese seed** — no es un problema exclusivo de OIJ, hay que resolverlo en equipo. Mientras tanto, `db/seed_cantones_TEMP_dev.sql` deja 6 cantones con geometría de relleno (no son los límites reales) solo para poder probar el flujo local; debe eliminarse cuando Integrante 1 cargue los límites reales desde SNIT.

Para pruebas locales sin depender de la descarga real: `etl/oij/reportes/muestra_prueba.csv` trae un CSV sintético con el mismo formato posicional (incluye un cantón fuera del seed, "CAÑAS", para comprobar que el aviso de "cantón sin match" funciona).

```bash
psql "$DATABASE_URL" -f db/seed_cantones_TEMP_dev.sql
cd etl/oij
python sync_oij.py --archivo reportes/muestra_prueba.csv --anio 2025
```

## Advertencia ética (obligatoria en el sistema)

Estas son **estadísticas agregadas por cantón**, nunca a nivel de persona. El sistema nunca debe insinuar que un cantón "peligroso" implica algo sobre sus habitantes, y la correlación entre seguridad e índice de viabilidad **no debe presentarse como causalidad**. Esta advertencia debe ser visible también en el frontend, cerca del Factor de Seguridad.

## Frecuencia de sincronización

Trimestral. El archivo se publica por año completo y se actualiza mensualmente según el portal, así que conviene fijar en equipo un año de referencia (`OIJ_ANIO_REFERENCIA`) y no mezclar años parciales en el índice.
