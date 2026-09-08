# Fuente OSINT: SNIT — Sistema Nacional de Información Territorial

**Responsable:** Integrante 1 (Diana)
**Factor del índice:** Factor Ambiental (25%)
**Fecha de consulta de los datos:** 2026-09-02
**Frecuencia de sincronización:** una vez, o semanal (estas capas casi no cambian)

## Qué aporta al sistema

Tres capas territoriales oficiales —áreas silvestres protegidas, corredores
biológicos e hidrografía— más los límites cantonales. Con ellas se calcula, por
cantón, un puntaje ambiental de 0 a 100 que responde a la pregunta del proyecto:
¿este cantón tiene naturaleza protegida cerca **y** todavía deja terreno donde
instalar un proyecto legalmente?

Además, esta fuente carga la tabla `cantones`, que es la unidad territorial
común contra la que se cruzan las cuatro fuentes del proyecto.

## Nodos y capas utilizadas

Confirmadas con `GetCapabilities` el 2026-09-02:

| tipo_capa | nodo WFS | capa (`typeName`) | features |
|---|---|---|---|
| `cantones` | `https://geos.snitcr.go.cr/be/IGN_5_CO/wfs` | `IGN_5_CO:limitecantonal_5k` | 84 |
| `area_protegida` | `https://geos1pne.sirefor.go.cr/wfs` | `PNE:areas_silvestres_protegidas` | 174 |
| `corredor_biologico` | `https://geos1pne.sirefor.go.cr/wfs` | `PNE:corredoresbiologicos` | 151 |
| `hidrografia` | `https://geos.snitcr.go.cr/be/IGN_200/wfs` | `IGN_200:reddrenaje_200k` | 6 331 |

## Cómo se consume

Protocolo **WFS** (Web Feature Service), estándar OGC. Dos pasos:

**1. `GetCapabilities`** — confirma el nombre exacto de las capas del nodo:

```
GET {nodo}?service=WFS&version=2.0.0&request=GetCapabilities
```

En Python se hace con `owslib.wfs.WebFeatureService`.

**2. `GetFeature`** — descarga las entidades, ya reproyectadas por el servidor:

```
GET {nodo}?service=WFS&version=2.0.0&request=GetFeature
    &typeNames={capa}
    &outputFormat=application/json
    &srsName=EPSG:4326
    &count={n}&startIndex={i}
```

## Formato de respuesta (ejemplo real, ASP)

```json
{
  "type": "Feature",
  "geometry": { "type": "Polygon", "coordinates": [[[-83.69, 10.93], "..."]] },
  "properties": {
    "codigo": "V01",
    "nombre_asp": "Barra del Colorado",
    "cat_manejo": "Refugio Nacional de Vida Silvestre",
    "descripcio": "Area terrestre protegida",
    "area_km2": 811.53
  }
}
```

## Normalización y carga

1. El servidor entrega EPSG:4326 gracias a `srsName` (el origen es CRTM05).
2. Los cantones van a `cantones`; las otras tres capas a `capas_snit`, con los
   atributos originales en `JSONB` para absorber la variabilidad entre nodos.
3. Cada corrida se registra en `sincronizaciones` con estado y cantidad.
4. Se guarda una copia local en `etl/snit/data/*.geojson` con la fecha de
   consulta, como respaldo para la demo.

## Cómo se calcula el Factor Ambiental

Vista materializada `v_factor_ambiental`, definida en `sync_snit.py`. Todas las
mediciones se reproyectan a **EPSG:5367 (CRTM05)**, que está en metros: medir
áreas en EPSG:4326 daría grados cuadrados, que no son unidad de superficie.

| sub-puntaje | peso | criterio |
|---|---|---|
| ASP | 50% | Banda, no binario: óptimo entre 5% y 30% del cantón protegido |
| Corredor biológico | 30% | Cobertura del cantón, con techo en 30% |
| Hidrografía | 20% | Densidad de drenaje (km/km²), normalizada por percentil |

**La banda del ASP es la decisión clave.** Un cantón sin nada protegido no
ofrece el entorno natural que busca un proyecto de ecoturismo; uno casi
enteramente protegido no deja terreno donde instalarse legalmente. Por eso
Heredia (84.8% protegido) puntúa 47 y Goicoechea (9.3% protegido, 65.9% en
corredor biológico) puntúa 100.

Se usa **percentil** y no min-max para la hidrografía porque la distribución
tiene cola larga: con min-max, unos pocos cantones aplastarían la escala.

> **Estos pesos y umbrales son una decisión del equipo, no un estándar
> oficial.** El Factor Ambiental es una inferencia construida sobre datos
> públicos, no un indicador publicado por el SNIT ni por el SINAC.

Resultado sobre los 84 cantones: mínimo 31.6, promedio 75.2, máximo 100.

## Cómo correrlo

```powershell
# ver qué capas publica cada nodo
python sync_snit.py --listar-capas

# descargar sin tocar la base
python sync_snit.py --capa cantones --dry-run

# cargar las 4 capas y calcular el factor
python sync_snit.py --todas --calcular-factor

# recargar desde el respaldo local si el nodo del SNIT está caído
python sync_snit.py --todas --desde-respaldo

# filtrar por bounding box (minlon,minlat,maxlon,maxlat)
python sync_snit.py --capa area_protegida --bbox=-85.9,10.1,-85.0,11.0 --dry-run
```

Sobre el `--bbox`: hay que escribirlo pegado con `=`, porque el valor empieza
con `-` y de lo contrario argparse lo interpreta como otra opción. El recuadro
se declara internamente como **CRS84** y no como EPSG:4326: en WFS 2.0 el
EPSG:4326 usa orden `latitud,longitud` mientras que CRS84 usa
`longitud,latitud`, y con el orden invertido el filtro cae en otra parte del
planeta y devuelve vacío sin dar error. Probado sobre Guanacaste: devuelve 35
de las 174 ASP, todas de esa zona. Las descargas con bbox se guardan en un
archivo aparte (`<capa>_bbox.geojson`) para no dejar incompleto el respaldo
nacional.

Las capas del proyecto son chicas y se traen completas; el filtro espacial hace
falta si alguien quisiera usar capas de mayor detalle, como
`IGN_25:caucedrenaje_25k`, con 118 136 features.

**Tiempos esperados.** La descarga de las cuatro capas tarda unos minutos. El
cálculo inicial del factor (`--calcular-factor`) y su refresco automático al
final de cada `--todas` tardan alrededor de 5 minutos cada uno: es el cruce
espacial de los 84 cantones a escala 1:5mil contra 6 656 geometrías. El script
avisa antes de empezar para que no parezca que se colgó. Una vez calculada, la
vista materializada responde en menos de un segundo.

Variables de entorno en `.env.example`: `SNIT_WFS_IGN_5_CO_URL`,
`SNIT_WFS_IGN_200_URL`, `SNIT_WFS_PNE_URL`, `SNIT_WFS_VERSION`,
`SNIT_WFS_TIMEOUT`, `SNIT_WFS_PAGINA`. Esta fuente **no requiere token ni
credenciales**.

## Retos encontrados

**1. Las capas del SINAC no están donde parecía.** En `geos.snitcr.go.cr` el
servicio WFS del nodo SINAC está deshabilitado (`Service WFS is disabled`). Las
áreas protegidas y los corredores biológicos se publican en un nodo aparte,
`geos1pne.sirefor.go.cr`, que se localizó recorriendo el directorio de nodos del
SNIT.

**2. El servidor del IGN reporta mal el conteo.** `numberMatched` devuelve **7**
para la capa de límites cantonales, que en realidad tiene **84**, y sin
`startIndex` entrega solo esas 7. Un ETL que confíe en el conteo del servidor
carga 7 cantones sin dar error. Por eso se pagina con `count` + `startIndex`
hasta recibir una página incompleta.

**3. El nodo PNE negocia WFS 1.1.0.** Rechaza `GetCapabilities` en 2.0.0 pero sí
acepta `GetFeature` 2.0.0 con paginación. El script reintenta con 1.1.0.

**4. La hidrografía a 1:25mil es inviable.** `IGN_25:caucedrenaje_25k` tiene
118 136 features. Se usa `IGN_200:reddrenaje_200k` (6 331), suficiente para una
densidad de drenaje por cantón.

**5. Las ASP incluyen áreas marinas.** De las 174, hay 18 marinas y 4 áreas
marinas de manejo. Se excluyen del factor: una ASP marina frente a la costa no
restringe el territorio del cantón.

**6. El cálculo espacial tardaba minutos en cada consulta.** Como vista normal,
PostGIS recalculaba las intersecciones cada vez que alguien la consultaba, lo
que dejaría la API colgada. Se convirtió en vista **materializada** con índice
único, refrescada al final de cada sincronización.

## Referencia oficial

- SNIT — Servicios OGC: https://www.snitcr.go.cr/ico_servicios_ogc
- Nodo SINAC (áreas protegidas y corredores): https://geos1pne.sirefor.go.cr/wfs
- Nodos IGN (límites cantonales, hidrografía): https://geos.snitcr.go.cr/