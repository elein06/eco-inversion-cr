# Fuente OSINT: SICOP (Sistema Integrado de Compras Públicas)

**Responsable:** Integrante 2
**Factor del índice:** Factor de Inversión Municipal (25%)
**Validado contra el servicio real el:** 2026-09-03

## Qué aporta

Contratos públicos de gobiernos locales relacionados con gestión ambiental,
usados como proxy de apoyo institucional de un cantón a proyectos de impacto.

## El módulo cambió: lo primero que hay que saber

El endpoint que traía el plan original,

```
https://www.sicop.go.cr/moduloPcont/pcont/rp/CE_MOD_DATOSABIERTOSVIEW.jsp
```

**devuelve HTTP 500**. SICOP se rehizo como aplicación Angular y el Módulo de
Descarga de Datos (Datos Abiertos) ahora vive en:

```
https://www.sicop.go.cr/app/module/pcont/public/ce-open-data
```

Esa página no trae los datos: es un cliente que habla con una API pública en
`https://prod-api.sicop.go.cr`, **sin token, sin cookie de sesión y sin
cabecera de autenticación**. Eso es lo que permitió automatizar la fuente en
vez de bajar archivos a mano, que era el plan original.

Nada de lo que sigue se adivinó: los códigos de reporte, los nombres de los
campos y el formato de las fechas se confirmaron observando las peticiones que
hace el propio módulo, y los nombres de columna salen del Diccionario de Datos
oficial que el módulo publica:

- [Diccionario de datos](https://www.sicop.go.cr/atDocs/Diccionario_de_datos_reporte_de_contratos_de_Datos_abiertos.pdf)
- [Diagrama ERD](https://www.sicop.go.cr/atDocs/diagrama_erd.pdf)

## Endpoints

La descarga **no es síncrona**. Son cuatro llamadas:

| Paso | Método y ruta | Qué hace |
|---|---|---|
| 1 | `POST /pcont/api/v1/public/ceOpenDataPublicController/requestDownload` | Encola el reporte. Devuelve `{reportId, status, codeReport, typeFile}` |
| 2 | `POST /bid/api/v1/public/coConfirmCodeProc/reqCode` | Manda un código alfanumérico al correo indicado. Devuelve `confirmId` |
| 3 | `POST /bid/api/v1/public/coConfirmCodeProc/confirmCode` | Valida el código. **Esto es lo que dispara la construcción del reporte** |
| 4 | `POST /bid/api/v1/public/coReport/checkDownload?reportId=N` | ¿Ya está? Cuerpo vacío = sí; `msg_not_builded_report` = todavía no |
| 5 | `GET /bid/api/v1/public/coReport/download?reportId=N` | Entrega el archivo |

Cuerpo del paso 1 (ejemplo real, reporte de Contratos):

```json
{
  "pageNumber": 0,
  "pageSize": 100,
  "tableSorter": { "sorter": "", "order": "desc" },
  "tableFilters": [],
  "formFilters": [
    { "field": "startDt",        "value": "2026-09-02T06:00:00.000Z" },
    { "field": "endDt",          "value": "2026-09-03T06:00:00.000Z" },
    { "field": "downloadFormat", "value": "csv" },
    { "field": "typeFile",       "value": "csv" },
    { "field": "reportType",     "value": "SV_CONT_0014" }
  ]
}
```

Respuesta:

```json
{ "reportId": 36713, "status": "V", "codeReport": "SV_CONT_0014", "typeFile": "csv" }
```

Detalles que cuesta descubrir y conviene no volver a descubrir:

- Las fechas van en **ISO 8601 UTC**, no en el `dd/MM/yyyy` que muestra la
  pantalla. Costa Rica es UTC-6 todo el año, así que la medianoche local del
  día pedido es `T06:00:00.000Z`.
- El formato del archivo lo decide `typeFile` (`csv`, `xlsx`, `json`).
  `downloadFormat` va siempre en `"csv"`: el módulo web lo manda así y el
  servidor lo ignora.
- La API rechaza el `User-Agent` por defecto de `requests` con HTTP 403. Hay
  que mandar `User-Agent` de navegador y `Origin: https://www.sicop.go.cr`.
- `checkDownload` responde **200 con texto plano**, no un JSON ni un 404.
- **Los encabezados del CSV no son los del Diccionario de Datos.** El PDF
  documenta los nombres internos de los campos; el archivo descargado trae
  encabezados legibles, separados por `;` y en **latin-1**. `normalizacion.py`
  acepta las dos formas de cada nombre:

  | En el CSV real | En el diccionario |
  |---|---|
  | `Número SICOP` | `NRO_SICOP` |
  | `Fecha de Notificación` | `FECHA_NOTIFICACION` |
  | `Cantidad` | `CANTIDAD_CONTRATADA` |
  | `Tipo Cambio` | `TIPO_CAMBIO_CRC` |
  | `Moneda` | `TIPO_MONEDA` |
  | `Cédula Empresa Proveedora` | `CEDULA_PROVEEDOR` |

- **El reporte de Contratos llega como un zip con dos CSV**: `Informacion de
  contratos.csv` (la cabecera) y `Lineas de contratos.csv` (de donde sale el
  monto).

## Limitación conocida: el código por correo

`requestDownload` encola el reporte, pero SICOP **no lo construye** hasta que
alguien confirma un código que el sistema envía a un correo electrónico. Se
comprobó: un reporte encolado sin confirmar siguió en `msg_not_builded_report`
45 minutos después.

Dos detalles del correo, verificados sobre uno real:

- **El código no es numérico.** Son 6-7 caracteres alfanuméricos y distingue
  mayúsculas (ejemplo real: `Lw45ef`). El formulario de SICOP lo valida con
  `minLength(6), maxLength(7)`.
- **El correo no identifica el reporte.** Llega desde `info@sicop.go.cr`, con
  asunto "Código verificación para reporte" y un cuerpo de una línea: "Para
  continuar con la gestión realizada, debe ingresar el siguiente código". Sin
  enlace, sin `reportId`, sin el nombre del reporte. Y si se piden los tres
  reportes seguidos, los tres correos llegan con segundos de diferencia, así
  que la hora tampoco desempata.

Por eso `--confirmar` acepta el código **sin** `--report-id` y lo prueba contra
las solicitudes pendientes: el `confirmId` que se guardó al pedir cada código
es lo que ata ese código a ese reporte, de modo que SICOP acepta exactamente
una combinación y rechaza las demás. Son a lo sumo tres intentos.

Es el único paso del ETL que necesita un dato personal, y por eso está aislado
en `etl/sicop/confirmacion.py` y solo corre cuando quien ejecuta el script pasa
su propio correo con `--correo`. El correo **no se guarda** en disco ni se
versiona; lo único que queda en `data/<reportId>.confirm.json` es el
`confirmId`, que no identifica a nadie.

Una vez confirmado el código, el resto (esperar y bajar) es automático.

## Reportes disponibles

Once secciones, cada una con su código. `python sync_sicop.py --listar-reportes`
las imprime con el detalle de por qué se usa o no cada una.

| Nombre corto | Código | Sección | Rango de fechas | ¿Se usa? |
|---|---|---|---|---|
| `solicitudes` | `SV_CONT_0008` | Solicitud de contratación | sí | no |
| `carteles` | `SV_CONT_0009` | Detalle pliego de condiciones | sí | **sí** |
| `aclaraciones` | `SV_CONT_0010` | Aclaraciones | sí | no |
| `recursos` | `SV_CONT_0011` | Recursos | sí | no |
| `ofertas` | `SV_CONT_0012` | Ofertas | sí | no |
| `adjudicaciones` | `SV_CONT_0013` | Adjudicaciones en firme | sí | no |
| `contratos` | `SV_CONT_0014` | Contratos | sí | **sí** |
| `ordenes` | `SV_CONT_0015` | Ordenes de pedido | sí | no |
| `instituciones` | `SV_CONT_0016` | Instituciones compradoras | no | **sí** |
| `proveedores` | `SV_CONT_0017` | Proveedores | no | no |
| `catalogo` | `SV_CONT_0018` | Catálogo de bienes y servicios | no | no |

## Por qué hacen falta tres reportes y no uno

Ningún reporte trae solo los cuatro datos que el proyecto necesita. Están
repartidos, y ese es el trabajo real de este ETL:

```
contratos (SV_CONT_0014)        NRO_CONTRATO, SECUENCIA, NRO_SICOP,
                                FECHA_NOTIFICACION
        |  NRO_CONTRATO + SECUENCIA
        v
líneas del contrato (7.2)       CANTIDAD_CONTRATADA, PRECIO_UNITARIO,
                                TIPO_MONEDA   ->  de aquí sale el MONTO
        |  NRO_SICOP
        v
carteles (SV_CONT_0009)         CEDULA_INSTITUCION, DESCRIPCION
                                -> de aquí sale el TEXTO que se clasifica
        |  CEDULA_INSTITUCION = CEDULA
        v
instituciones (SV_CONT_0016)    NOMBRE_INSTITUCION, PROVINCIA, CANTON
                                -> de aquí sale el CANTÓN
```

Dos consecuencias que vale la pena decir en la exposición:

1. **El reporte de Contratos no trae ni el monto ni la descripción.** El monto
   está en las líneas del contrato y la descripción solo existe en el cartel.
2. **El cantón sale del catálogo oficial de instituciones**, con sus campos
   `PROVINCIA`/`CANTON`/`DISTRITO`, no de partir el nombre de la municipalidad
   con una expresión regular, que era lo que planteaba el diseño original.

### Cálculo del monto

Por línea de contrato:

```
monto = CANTIDAD_CONTRATADA * PRECIO_UNITARIO
        - DESCUENTO + IVA + OTROS_IMPUESTOS + ACARREOS
```

y se suman las líneas de un mismo `(NRO_CONTRATO, SECUENCIA)`. Cuando la moneda
no es `CRC`, el monto se convierte a colones con el tipo de cambio que SICOP
registró en la línea.

**El problema:** SICOP deja ese campo en **0 más de la mitad de las veces** —
947 de 1 768 líneas en moneda extranjera, en el reporte de contratos de
2026-06 a 2026-09. Sin un respaldo, esos montos se quedan en dólares o euros y
después se suman junto a los colones como si fueran la misma unidad, inflando
el factor del cantón.

**La solución, sin fuente externa** (el BCCR quedó fuera del proyecto para no
tramitar su token): cuando falta el tipo de cambio se usa la **mediana de los
que el propio archivo sí trae para esa moneda**. Es del mismo periodo que los
contratos y queda auditable dentro del dato. Lo que ni así se puede convertir
se carga en su moneda original, y `v_factor_inversion` solo suma
`moneda = 'CRC'`, de modo que nunca contamina el puntaje.

Efecto medido sobre el reporte real:

```
antes:  1014 CRC + 250 USD + 18 EUR  ->  ¢39 424 424 782  (mezclando unidades)
ahora:  1282 CRC                     ->  ¢41 409 660 445
```

## Criterio de clasificación "ambiental"

No se usa machine learning. Es una lista de palabras clave agrupadas en seis
categorías, que se busca con una expresión regular sobre `DESCRIPCION`, con el
texto normalizado sin tildes y exigiendo palabra completa (`\b`).

`python sync_sicop.py --criterio` imprime la lista completa y actualizada. Las
seis categorías son: `residuos`, `reciclaje`, `agua`, `areas_verdes`,
`infraestructura_verde`, `gestion_ambiental`. Cuando una descripción encaja en
varias, gana la primera según ese orden, que va de lo específico a lo genérico.

El criterio vive completo en [`etl/sicop/clasificacion.py`](../etl/sicop/clasificacion.py)
y se eligió así a propósito: se lee en 60 líneas, siempre da el mismo resultado
para la misma entrada, y cuando se equivoca se ve exactamente por qué palabra
se equivocó.

**Riesgo conocido, documentado en vez de disimulado:** habrá falsos positivos
(un contrato de "recolección de residuos electrónicos de oficina" no es un
proyecto ambiental) y falsos negativos (un contrato ambiental descrito con
palabras que no están en la lista). Exigir palabra completa ya evita los casos
obvios —"agua" no encuentra "aguacate" ni "paraguas"—, pero no elimina el
problema.

## Nota de alcance: solo gobiernos locales

Por defecto solo se cuentan contratos de municipalidades y concejos municipales
de distrito (`--todas-instituciones` desactiva el filtro).

La razón es que el cantón que trae el catálogo de instituciones es el
**domicilio de la institución**, no el lugar donde se ejecuta la obra. Para una
municipalidad las dos cosas coinciden; para el AyA o el ICE, no: un contrato de
alcantarillado del AyA ejecutado en Limón aparecería como inversión del cantón
donde está su sede. Contarlo inflaría a unos pocos cantones y vaciaría al
resto.

Es una decisión que restringe el alcance del factor —mide **inversión
municipal** ambiental, no inversión pública ambiental total— y hay que decirlo
así en la exposición.

## Normalización y carga

1. `cargar_tablas` lee los archivos bajados (csv, xlsx, json o zip) y decide
   qué reporte es cada uno **por sus columnas**, no por el nombre del archivo:
   el nombre que manda SICOP en `Content-Disposition` no es estable.

   **Descargas que se solapan.** `--cargar` sin `--archivo` toma todo `data/`,
   donde suele quedar más de una descarga del mismo reporte con rangos que se
   pisan (una prueba corta y la buena, o dos corridas semanales). Las filas
   repetidas se descartan comparando la fila completa —dos descargas del mismo
   contrato traen los mismos valores en todas las columnas— y el ETL informa
   cuántas quitó. Sin eso, el mismo contrato entra dos veces y el monto del
   cantón se duplica sin que nada avise: con un reporte de prueba de 735
   contratos junto al bueno de 19 157, la tabla quedaba en 19 892.

   `data/` está en `.gitignore`, así que nada de esto llega al repositorio.
2. `construir_dataset` hace los tres joins, calcula el monto, aplica el filtro
   de gobiernos locales y clasifica.
3. `cargar_contratos` resuelve `canton_id` contra `cantones` (por nombre +
   provincia, y por nombre solo cuando es inequívoco) e inserta en
   `contratos_ambientales`.

   **Cantones renombrados.** SICOP conserva en su catálogo nombres de cantón
   derogados, mientras que `cantones` viene del IGN con los vigentes. Sin
   traducirlos, esos cantones quedan sin `canton_id` y su inversión ambiental
   no aparece en el mapa. Son exactamente cuatro, verificados contra el reporte
   real (96 gobiernos locales, 92 resolvían):

   | En SICOP | Vigente (IGN) | Ley |
   |---|---|---|
   | Alfaro Ruiz | Zarcero | 9268 (2014) |
   | Aguirre | Quepos | 9331 (2015) |
   | Valverde Vega | Sarchí | 9440 (2017) |
   | León Cortés | León Cortés Castro | nombre completo en la capa del IGN |

   La equivalencia está en `CANTONES_RENOMBRADOS`, en
   [`etl/sicop/carga_postgres.py`](../etl/sicop/carga_postgres.py). Con ella
   resuelven los 96.
4. Se registra la corrida en `sincronizaciones` con `fuente_id` = SICOP,
   incluyendo cuántas filas se perdieron en cada paso.

**Idempotencia:** `contratos_ambientales` no tiene llave natural en
`db/schema.sql`, que es el esquema compartido del equipo. En vez de tocarlo, la
carga borra los contratos SICOP del periodo que va a recargar y los vuelve a
insertar dentro de la misma transacción. Reejecutar deja la tabla igual que si
se hubiera corrido una sola vez, sin afectar periodos ya cargados.

## Factor de Inversión Municipal

La vista `v_factor_inversion` (creada por `--calcular-factor`, definida en
[`etl/sicop/factor_inversion.py`](../etl/sicop/factor_inversion.py)) convierte
los contratos en un puntaje 0-100 por cantón, con tres sub-puntajes:

| Sub-puntaje | Qué mide | Peso interno |
|---|---|---|
| `sub_monto` | Monto ambiental por habitante, en percentil | 50% |
| `sub_cantidad` | Cantidad de contratos ambientales, en percentil | 30% |
| `sub_diversidad` | Cuántas de las 6 categorías aparecen | 20% |

Decisiones detrás de esos números, todas del equipo y ninguna oficial:

- **Por habitante, no absoluto**, para no premiar a los cantones grandes solo
  por ser grandes. Si `cantones.poblacion` está vacía, se cae al monto
  absoluto y la vista lo dice en su columna `base_monto`.

  > **Estado actual (2026-09-05):** `cantones.poblacion` está en NULL en los 84
  > cantones, así que `base_monto` sale `monto_absoluto` en todos y **el
  > sub-puntaje de monto NO está normalizado por habitante**. El factor que se
  > calcula hoy sí premia a los cantones grandes: es exactamente el sesgo que
  > la decisión de arriba quería evitar. Hay que decirlo en la exposición
  > mientras siga así.
  >
  > La misma columna vacía afecta al Factor de Seguridad del OIJ, que sin
  > población usa el conteo bruto de delitos en vez de la tasa por 10 000
  > habitantes (`backend/app/indice.py`). Se arregla de una para las dos
  > fuentes cargando la población con
  > [`etl/common/load_poblacion.py`](../etl/common/load_poblacion.py), que pide
  > un CSV del INEC; ver el encabezado de ese archivo.
- **Percentil y no min-max**, porque el gasto municipal tiene cola muy larga:
  un solo contrato de alcantarillado de miles de millones aplastaría la escala
  de los otros 83 cantones.
- **La cantidad y la diversidad corrigen** el caso del cantón con un único
  contrato gigante, que no demuestra el mismo compromiso sostenido.
- **Un cantón sin contratos ambientales queda en 0, no en NULL.** La ausencia
  de inversión municipal ambiental es información, no un dato faltante.

A diferencia de `v_factor_ambiental` del SNIT, esta es una vista **normal** y
no materializada: son sumas y conteos sin geometría, se calculan en
milisegundos, y así queda al día sola en cuanto el ETL inserta contratos.

## Cómo correrlo

```bash
cd etl/sicop
pip install -r requirements.txt

# Ver qué reportes existen y con qué criterio se clasifica
python sync_sicop.py --listar-reportes
python sync_sicop.py --criterio

# 1. Encolar los tres reportes y pedir el código de confirmación
python sync_sicop.py --solicitar --todos \
    --desde 2026-06-01 --hasta 2026-09-01 --correo yo@ejemplo.com

# 2. Confirmar con el código que llegó al correo (llega uno por reporte).
#    El script ubica solo a qué reporte pertenece, espera a que SICOP lo
#    construya y lo baja a data/
python sync_sicop.py --confirmar --codigo Lw45ef

#    Para ver qué reportId es cuál y cuáles faltan:
python sync_sicop.py --pendientes

# 3. Clasificar y revisar sin tocar la base
python sync_sicop.py --cargar --dry-run

# 4. Cargar y calcular el factor
python sync_sicop.py --cargar --calcular-factor
```

> **Orden importante:** el ETL del SNIT va primero. Es el que llena la tabla
> `cantones`, contra la que este ETL resuelve el `canton_id`.

Si un reporte tarda más que `SICOP_ESPERA_MAX`, no se pierde: se retoma con
`--descargar --report-id N`, sin volver a encolarlo.

## Frecuencia de sincronización

Semanal. Los reportes son una réplica del repositorio principal de SICOP y
pueden ir hasta 24 horas atrasados respecto al sistema en vivo (lo advierte el
propio módulo).

## Variables de entorno

```
SICOP_DATOS_ABIERTOS_URL=https://www.sicop.go.cr/app/module/pcont/public/ce-open-data
SICOP_API_BASE_URL=https://prod-api.sicop.go.cr
SICOP_TIMEOUT=120
SICOP_ESPERA_MAX=1800
SICOP_ESPERA_INTERVALO=30
```
