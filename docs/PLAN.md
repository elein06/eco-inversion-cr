# Eco-Inversión Costa Rica — Plan de Proyecto
### Investigación 2 · Sistema Web con Fuentes OSINT de Costa Rica

## Resumen del proyecto

Eco-Inversión Costa Rica es una plataforma tipo mapa interactivo dirigida a ONGs, emprendedores sociales e inversionistas que buscan el cantón más adecuado para establecer proyectos de impacto (ecoturismo, reciclaje, agricultura sostenible). El sistema cruza cuatro fuentes OSINT distintas para calcular, por zona, un Índice de Viabilidad que combina condición ambiental, apoyo institucional, conectividad y seguridad. La fuente económica original (BCCR) se reemplaza por el Poder Judicial / OIJ, lo que evita el trámite de token del servicio SOAP del Banco Central y además añade una dimensión de seguridad que conecta directamente con el enfoque del curso.

## Reparto de fuentes y forma de consumo

### Integrante 1 — SNIT (áreas protegidas, corredores biológicos, hidrografía)

Se consume por servicio WFS. El primer paso, antes de escribir una sola línea de código, es hacer un `GetCapabilities` al nodo SNIT correspondiente para confirmar el nombre exacto de las capas disponibles, porque la oferta varía según nodo. Con el nombre confirmado, se piden `GetFeature` filtrando por bounding box o por cantón, con salida en GML o GeoJSON. En Python, la librería `owslib` está hecha justo para esto; el resultado se normaliza a GeoJSON (EPSG:4326) y se guarda en PostgreSQL con la extensión PostGIS, que permite hacer preguntas espaciales directamente en SQL, como "qué zonas quedan fuera de un área protegida". Como estas capas casi no cambian, un script de sincronización que corre una sola vez o semanalmente es suficiente.

### Integrante 2 — SICOP (inversión municipal ambiental)

SICOP no ofrece una API REST limpia, así que la fuente son reportes descargables en Excel/CSV/JSON desde su módulo de datos abiertos. La parte no trivial es detectar cuáles contratos son "ambientales": se define una lista de palabras clave (residuos, reciclaje, arborización, alcantarillado, gestión ambiental, infraestructura verde) que se busca en la descripción del objeto contractual mediante regex. No hace falta machine learning — reglas simples son suficientes y son más fáciles de justificar en la exposición porque se puede explicar el criterio exacto. Con Python, `pandas` y `openpyxl` cubren la lectura y limpieza; el resultado se guarda en una tabla `contratos_ambientales` (institución, monto, fecha, municipalidad, categoría detectada) en la misma base compartida. La descarga y clasificación se corre de forma periódica, por ejemplo semanal.

### Integrante 3 — OpenStreetMap / Overpass API (conectividad e infraestructura)

Se consulta la Overpass API con Overpass QL para obtener puntos de interés relevantes (centros de acopio, escuelas, vías principales) dentro del área de cada zona candidata. En Python, `overpy` simplifica la construcción de la consulta, y `osm2geojson` convierte el resultado a GeoJSON. Como las instancias públicas de Overpass tienen límites de uso, los resultados se cachean en la base de datos con una vigencia razonable (por ejemplo, siete días) en vez de volver a consultar en cada carga del mapa — esto es justo lo que pide el enunciado del curso al usar esta fuente.

### Integrante 4 — Poder Judicial / OIJ (seguridad, reemplaza al BCCR)

El portal de Datos Abiertos del Poder Judicial publica estadísticas policiales por cantón y por año, construido sobre CKAN, con recursos en CSV, XLS/XLSX, XML y RDF, sin necesidad de token. Se descarga el recurso correspondiente (algunos datasets de CKAN también exponen un endpoint tipo `/api/3/action/datastore_search` si se prefiere consumir vía API en vez de archivo). Con `pandas` se limpia y se calcula una tasa de incidencia normalizada por cantón (por ejemplo, delitos por cada 10,000 habitantes, o un score relativo entre cantones si no quieren depender de datos de población). Se guarda en una tabla `estadisticas_seguridad` (cantón, tipo de delito, cantidad, año). Es importante documentar en el README que estas son estadísticas agregadas: el sistema nunca debe insinuar que un cantón "peligroso" implica algo sobre sus habitantes, y la correlación con el índice de viabilidad no debe presentarse como causalidad. La sincronización puede ser trimestral, ya que estos datasets no se actualizan con mucha frecuencia.

## Arquitectura general

Se recomienda unificar el stack en Python para simplificar la coordinación del equipo, ya que tres de las cuatro fuentes (SNIT, SICOP, OIJ) ya usan `pandas`/`owslib` de forma natural. El backend puede construirse con FastAPI, exponiendo una API propia con endpoints normalizados (`/zonas`, `/contratos-ambientales`, `/infraestructura`, `/seguridad`, `/indice-viabilidad`) que es lo único que el frontend consume — nunca habla directo con SNIT, SICOP, OSM o el Poder Judicial. La base de datos es PostgreSQL con PostGIS, compartida por los cuatro integrantes según un esquema que se define en equipo antes de empezar a programar cada quien por su lado. El frontend puede ser React con Leaflet (más simple de aprender) o MapLibre GL (mejor rendimiento con varias capas) para el mapa interactivo, con un panel lateral que muestra el puntaje y permite filtrar por criterio.

Para desarrollo local, Docker Compose con un contenedor de Postgres+PostGIS evita que cada quien instale algo distinto. Para la demo final, un Postgres gestionado con PostGIS (Supabase o Neon) más un hosting simple del backend (Render o Railway) y del frontend (Vercel) evita depender de que la laptop de alguien esté encendida el día de la exposición.

## Índice de viabilidad — metodología

El índice se calcula por cantón o zona, en una escala de 0 a 100, como una suma ponderada de cuatro factores, uno por fuente:

Índice = 25% × Factor Ambiental (SNIT: fuera de área protegida o corredor biológico puntúa alto) + 25% × Factor de Inversión Municipal (SICOP: monto normalizado de contratos ambientales del cantón) + 25% × Factor de Conectividad (OSM: densidad de infraestructura clave cercana) + 25% × Factor de Seguridad (OIJ: inverso de la tasa de incidencia delictiva normalizada).

Los pesos son una decisión propia del equipo, no un estándar oficial, y deben quedar documentados como tal en el README y explicados en la exposición — es exactamente la distinción entre dato e inferencia que pide el enunciado del curso.

## Estructura sugerida del repositorio

```
/etl/snit          → script de Integrante 1 (WFS → GeoJSON → PostGIS)
/etl/sicop         → script de Integrante 2 (descarga + clasificación + carga)
/etl/osm           → script de Integrante 3 (Overpass → GeoJSON → caché)
/etl/oij           → script de Integrante 4 (CKAN → estadísticas → carga)
/backend           → API propia en FastAPI + cálculo del índice
/frontend          → mapa (React + Leaflet/MapLibre) + panel de resultados
/docs              → un archivo por fuente: endpoint, formato, ejemplo de respuesta
.env.example       → variables de entorno documentadas, sin secretos reales
README.md          → objetivo, fuentes, responsables, arquitectura, cómo correr el proyecto
```

## Plan de trabajo en 2 semanas

Con solo dos semanas no hay margen para que las cuatro etapas sean secuenciales: la validación de fuentes y el arranque del backend tienen que ir en paralelo desde el día 1, y el frontend debe empezar con datos de prueba (mock) en vez de esperar a que las cuatro fuentes estén cargadas.

**Semana 1, días 1–2 — Definición y prueba aislada.** Reunión de equipo el día 1 para fijar el esquema de la base de datos compartida (tablas, formato de geometría GeoJSON/EPSG:4326) antes de que cada quien programe por su lado. En paralelo, cada integrante confirma que puede consumir su fuente de forma aislada (imprimir el JSON/GeoJSON en consola es suficiente). Aquí se detecta rápido si alguna capa de SNIT no existe en el nodo elegido o si algún dataset del OIJ no está disponible, para sustituirla sin perder tiempo. Ese mismo día 1 o 2, una persona ya puede empezar el esqueleto del backend (rutas de la API) usando datos falsos.

**Semana 1, días 3–5 — ETL y carga en paralelo.** Cada integrante escribe su script de normalización y lo conecta a la base compartida. El backend avanza en paralelo consumiendo lo que ya vaya quedando cargado, aunque sea de una sola fuente. Meta de cierre de semana: las cuatro tablas con datos reales, aunque sea parcial.

**Semana 2, días 1–3 — Backend completo, índice y frontend conectado.** Se termina la API propia con el cálculo del Índice de Viabilidad, y el frontend deja de usar datos falsos para conectarse a la API real. Este es el tramo más apretado del cronograma, así que conviene que todo el equipo esté disponible estos días en vez de dividirse por fuente.

**Semana 2, días 4–5 — Pulido, README y ensayo.** Se completa el README (objetivo, fuentes, responsables, instrucciones de instalación, `.env.example`), se revisa que no queden secretos en el repositorio, y se ensaya la demo en vivo al menos una vez completa antes de la exposición. Estos dos últimos días funcionan como colchón para resolver imprevistos, así que no conviene dejar tareas nuevas pendientes para ellos.

## Riesgos y cómo mitigarlos

La disponibilidad exacta de la capa de corredores biológicos en SNIT depende del nodo, así que se verifica en la semana 1 y se sustituye por otra capa territorial si no existe. La clasificación de contratos "ambientales" en SICOP por palabras clave va a tener imprecisión inevitable; se documenta el criterio usado en vez de presentarlo como perfecto. Las instancias públicas de Overpass tienen límites de uso, por lo que se cachean resultados y se evitan consultas repetidas innecesarias. Los datasets del OIJ pueden tener periodicidad distinta entre recursos, así que conviene fijar desde el inicio con qué año o rango de años va a trabajar el equipo para que sea consistente en todo el sistema.

## Checklist según la rúbrica del curso

Integración y consumo real de las cuatro fuentes, con transformación de datos y capacidad demostrable (2%): cada fuente aporta un factor visible del índice, no solo una tabla aislada. Sistema web funcional con interfaz útil (1.5%): mapa interactivo con filtros y panel de puntaje. Calidad técnica y GitHub (0.5%): repositorio organizado como en la estructura sugerida arriba, README completo, variables de entorno documentadas sin secretos. Exposición y demostración (1%): explicar el problema, por qué se eligieron estas cuatro fuentes, cómo se calcula el índice, la arquitectura, una demo en vivo, y los retos encontrados (capa de SNIT, clasificación de SICOP, límites de Overpass).

## Notas de diseño del esquema de base de datos

1. `cantones` es el eje central. Todas las fuentes (SNIT, SICOP, OSM, OIJ) reportan datos que se pueden atar a un cantón mediante `canton_id`, que es justo la unidad que necesita el cálculo del Índice de Viabilidad. Sin este eje común, calcular el índice requeriría cruces espaciales repetidos en cada consulta.

   `fuentes` + `sincronizaciones` son el mecanismo de trazabilidad y manejo de errores que pide el documento de requisitos (sección "guardar procedencia... fuente y fecha de consulta" y "manejo razonable de errores"). Cada corrida de un ETL escribe un registro con estado (`exito`/`error`/`parcial`), así el equipo puede mostrar en la demo qué pasa si SNIT o Overpass no responden, sin tener que improvisarlo esa semana.

   `fecha_consulta` en cada tabla de datos (no solo en el log) permite mostrar "estos datos son de tal fecha" en el frontend, que es un punto explícito de evaluación.

   `geom` con PostGIS y GIST index en `cantones`, `capas_snit` e `infraestructura_osm`: sin índice espacial, cualquier consulta tipo "qué zonas están fuera de un área protegida" sería lenta apenas la tabla crezca.

   `atributos JSONB` en `capas_snit`: como el plan lo anota, los atributos de las capas WFS varían según el nodo SNIT. En vez de forzar columnas fijas que se rompan si cambia el nodo, JSONB absorbe esa variabilidad sin migraciones.

2. `valido_hasta` en `infraestructura_osm`: implementa directamente la caché de 7 días que exige Overpass — el backend solo re-consulta si `now() > valido_hasta`, sin necesitar lógica aparte.

   `estadisticas_seguridad` nunca referencia personas, solo agregados por cantón/tipo de delito/año — alineado con la advertencia del curso de no convertir estadísticas en afirmaciones sobre individuos.

   `indice_viabilidad` guarda `pesos_usados` como JSONB, no hardcodeado en el código del backend. Esto es clave para la exposición: se puede mostrar exactamente qué pesos se usaron en cada cálculo y justificar que es una decisión del equipo, no un estándar oficial.

   `poblacion` en `cantones` es un dato de referencia estático (INEC), necesario para normalizar la tasa de criminalidad del OIJ (delitos por 10,000 habitantes) — no es una "quinta fuente", es dato auxiliar.
