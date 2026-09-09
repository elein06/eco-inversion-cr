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

1. `sync_oij.py` lee el recurso (CSV real del PJ, sin encabezado — ver el
   docstring del script para el formato posicional verificado; `datastore_search`
   queda como *fallback* no confirmado para este dataset).
2. Limpiar con `pandas`: normalizar nombre de cantón contra `cantones.nombre`, tipo de delito, año.
3. Insertar el **agregado** (cantón + tipo de delito + año → cantidad) en
   `estadisticas_seguridad` (ver [db/schema.sql](../db/schema.sql)). La
   tasa normalizada por cantón (delitos por 10 000 habitantes, o el score
   relativo si no hay `poblacion`) ya **no** se calcula acá: vive en la
   vista `v_factor_seguridad` — ver la sección de abajo.
4. Registrar la corrida en `sincronizaciones` (`fuente_id` = OIJ).

## Advertencia ética (obligatoria en el sistema)

Estas son **estadísticas agregadas por cantón**, nunca a nivel de persona. El sistema nunca debe insinuar que un cantón "peligroso" implica algo sobre sus habitantes, y la correlación entre seguridad e índice de viabilidad **no debe presentarse como causalidad**. Esta advertencia debe ser visible también en el frontend, cerca del Factor de Seguridad.

Está implementada en tres lugares a la vez, no solo documentada: como valor
por defecto del campo `advertencia` en cada fila de `/indice-viabilidad`
(`backend/app/schemas.py`), como campo `advertencia` que acompaña **todos**
los endpoints de `/seguridad` (`backend/app/routers/seguridad.py`), y
renderizada en rojo al pie del panel de seguridad del frontend
(`frontend/src/OIJ/components/PanelSeguridadCanton.tsx`) — nunca
hardcodeada dos veces: el frontend siempre muestra el texto que le manda
el backend.

## Factor de Seguridad — vista y endpoint

`etl/oij/factor_seguridad.py` define `v_factor_seguridad`: una vista normal
(no materializada, como `v_factor_conectividad` de OSM) que convierte las
estadísticas cargadas en el Factor de Seguridad del Índice de Viabilidad,
normalizado 0-100 — igual arquitectura que `v_factor_ambiental` (SNIT),
`v_factor_inversion` (SICOP) y `v_factor_conectividad` (OSM).
`backend/app/indice.py` solo lee esa vista, no recalcula nada.

Metodología: se suma la cantidad de incidentes por cantón (todos los tipos
y años cargados juntos), se calcula una tasa por cada 10 000 habitantes
cuando el cantón tiene `poblacion` (si no, se usa el total crudo), y esa
tasa se normaliza min-max contra los **84 cantones, con y sin datos** (no
solo los que tienen algo cargado) y se **invierte**: a menor tasa de
incidencia, mayor Factor de Seguridad. Es una decisión del equipo, no un
indicador oficial.

Columnas: `canton_id`, `codigo_ine`, `nombre`, `provincia`, `poblacion`,
`total_delitos`, `tasa_incidencia`, `factor_seguridad`. El backend la
expone en:

- `GET /seguridad/factor` — los 84 cantones con su desglose
- `GET /seguridad/factor/{canton_id}` — uno solo
- `GET /seguridad/resumen` — totales por tipo de delito y año (no depende
  de la vista, responde aunque no se haya corrido `--calcular-factor`)

Si `v_factor_seguridad` todavía no existe, `/seguridad/factor` responde
`503` con el comando que falta correr — mismo criterio que
`/inversion/factor` (SICOP) e `/infraestructura/factor` (OSM). Se crea con:

```bash
cd etl/oij
python sync_oij.py --calcular-factor
```

(solo, o combinado con una carga: `python sync_oij.py --archivo
reportes/PJCROD_POLICIALES_V1-2025.csv --anio 2025 --calcular-factor`).

**Cambio respecto a versiones anteriores del índice:** antes, el cálculo
vivía en `backend/app/indice.py::_factor_seguridad` y se ejecutaba en cada
llamada a `/indice-viabilidad/recalcular` directo sobre `cantones` /
`estadisticas_seguridad`, sin depender de ninguna vista — por eso siempre
devolvía un resultado (50 para todos, por falta de variación) incluso sin
haber corrido nunca el ETL del OIJ. Ahora, si nadie ha corrido
`sync_oij.py --calcular-factor` en la base, el Factor de Seguridad queda en
0.0 para todos los cantones — igual criterio que ya usan ambiental,
inversión y conectividad cuando su vista respectiva no existe. Una vez que
la vista SÍ existe (aunque `estadisticas_seguridad` siga vacía), el
resultado sigue siendo 50 para todos, como antes. Documentado también en
`etl/oij/factor_seguridad.py` e `indice.py`.

## Frecuencia de sincronización

Trimestral — estos datasets no se actualizan con mucha frecuencia.

## Año de referencia (`OIJ_ANIO_REFERENCIA`) — un solo año, nunca mezclados

El equipo fija desde el inicio un único año de referencia para el Factor de
Seguridad, en `OIJ_ANIO_REFERENCIA` (ver [.env.example](../.env.example)):
los recursos del OIJ pueden tener periodicidad distinta entre sí, y sumar
estadísticas de varios años sin distinguir haría el factor incomparable
entre cantones — uno con datos de dos años cargados no sería comparable
con uno que solo tiene uno.

Está implementado, no solo declarado, en dos puntos (`etl/oij/factor_seguridad.py`
define `ANIO_REFERENCIA` a partir de esa variable y ambos lo importan):

- **Carga** (`sync_oij.py`): si no se pasa `--anio` explícito, usa
  `OIJ_ANIO_REFERENCIA` como filtro por defecto al agrupar el CSV. Si
  ninguno de los dos está fijado y el archivo trae más de un año, avisa por
  consola y carga todo tal cual (útil para archivar datos crudos), pero deja
  claro que el cálculo del factor se va a negar a correr mientras eso siga
  así.
- **Cálculo del factor** (`sync_oij.py --calcular-factor`, que crea
  `v_factor_seguridad`): resuelve el año con esta prioridad — (1)
  `OIJ_ANIO_REFERENCIA` si está fijada, sin importar qué haya en la tabla;
  (2) si no, y `estadisticas_seguridad` tiene datos de un único año, lo usa
  automáticamente; (3) si no, y hay datos de **dos o más años distintos**,
  se niega a crear la vista y explica cómo resolverlo (fijar la variable, o
  borrar las filas de los años que sobran) — mezclarlos en silencio
  produciría un Factor de Seguridad engañoso.

Verificado en la práctica: con datos de un solo año, el cálculo corre solo
sin configuración adicional; insertando a mano una fila de un año distinto,
`--calcular-factor` se niega con el mensaje de arriba; fijando
`OIJ_ANIO_REFERENCIA` al año correcto, vuelve a correr usando solo ese año e
ignorando el resto.
