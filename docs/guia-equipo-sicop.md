# Guía para el equipo — cómo funciona SICOP y cómo verlo

Este documento es para que cualquiera del equipo pueda levantar el proyecto en
su máquina y ver el Factor de Inversión Municipal ya funcionando, sin tener que
adivinar nada.

**Lo primero que hay que saber:** SICOP no deja bajar un reporte de una. Lo
construye de forma asíncrona y **exige confirmar un código que manda por
correo**. Eso significa que el camino completo pide un correo electrónico y
unos minutos de espera.

Por eso hay dos caminos, y conviene elegir antes de empezar:

| | Camino A — atajo | Camino B — completo |
|---|---|---|
| **Para quién** | Solo querés ver los datos funcionando | Querés reproducir la descarga o cambiar el rango de fechas |
| **Necesita correo** | No | Sí |
| **Tarda** | ~2 minutos | ~15-30 minutos |
| **Cómo** | Te paso los 3 archivos ya bajados | Los pedís vos a SICOP |

Los archivos descargados **no están en el repositorio** (`.gitignore` excluye
`etl/**/data/*`). Para el Camino A pedímelos y los pegás en `etl/sicop/data/`.

---

## Paso a paso

### 0. Requisitos

- Docker Desktop instalado **y abierto** (el engine tiene que estar corriendo,
  no basta con tenerlo instalado).
- Python 3.10 o superior.
- Solo para el Camino B: un correo electrónico al que puedas entrar en el
  momento.

### 1. Traer el código

```powershell
git pull origin main
```

### 2. Variables de entorno (una sola vez)

```powershell
cd C:\ruta\a\eco-inversion-cr
copy .env.example .env
```

Si el puerto 5432 ya lo ocupa un Postgres instalado en tu máquina, abrí el
`.env` y cambiá `POSTGRES_PORT` (por ejemplo a `5433`). **Importante:** si lo
cambiás, cambiá también el puerto dentro de `DATABASE_URL`, que es la que leen
los ETL y el backend:

```
POSTGRES_PORT=5433
DATABASE_URL=postgresql://eco_inversion:changeme@127.0.0.1:5433/eco_inversion_cr
```

### 3. Levantar la base de datos

```powershell
docker compose up -d db
docker ps
```

Tiene que aparecer `eco-inversion-db` con estado `(healthy)`. Si dice
`(health: starting)`, esperá unos segundos y volvé a correr `docker ps`.

### 4. Cargar la tabla `cantones` (una sola vez, la necesitan las 4 fuentes)

**Este paso va antes que SICOP, sin excepción.** El ETL de SICOP liga cada
contrato a un cantón, así que si la tabla está vacía se detiene con este error:

```
RuntimeError: La tabla `cantones` está vacía. El ETL del SNIT (Integrante 1)
es el que la llena y va primero
```

```powershell
cd etl\common
pip install psycopg2-binary python-dotenv
python load_cantones.py --geojson ..\..\db\cantones_cr.geojson
cd ..\..
```

Tienen que quedar 84 cantones.

### 5. Instalar las dependencias de SICOP

```powershell
cd etl\sicop
pip install -r requirements.txt
```

### 6-A. Camino A — con los archivos que ya bajé

Pegá los 3 archivos en `etl\sicop\data\` y saltá directo al paso 7:

```
36728_Reporte de detalle pliego de condiciones.zip
36742_Reporte de instituciones compradoras.csv
36749_Reporte de contratos.zip
```

Los `.meta.json` que los acompañan son opcionales, pero conviene copiarlos: son
la trazabilidad de la descarga (endpoint, `reportId`, fecha de consulta) y es lo
que hace defendible la corrida en la exposición.

Los `.confirm.json` **no hacen falta** — son estado de mi sesión y sus códigos
ya están usados.

### 6-B. Camino B — pedirle los reportes a SICOP vos mismo

Antes de nada, mirá qué hay y con qué criterio se clasifica. Ninguno de estos
dos comandos toca la red ni la base:

```powershell
python sync_sicop.py --listar-reportes
python sync_sicop.py --criterio
```

**Paso 1 — encolar los tres reportes y pedir los códigos.**

```powershell
python sync_sicop.py --solicitar --todos --desde 2026-06-01 --hasta 2026-09-01 --correo tucorreo@ejemplo.com
```

Esto encola `carteles`, `contratos` e `instituciones`, y le pide a SICOP que te
mande el código de confirmación de cada uno. **Sin `--correo` el reporte se
queda encolado para siempre**: SICOP no empieza a construirlo hasta que alguien
confirma. (Se comprobó dejando uno esperando 45 minutos.)

**Paso 2 — confirmar cada código.**

Te van a llegar **tres correos**, con el asunto *"Código verificación para
reporte"*. El problema: **ninguno dice a qué reporte pertenece**, no traen
enlace ni número de reporte, y si pediste los tres seguidos llegan con segundos
de diferencia, así que la hora tampoco desempata.

La solución es no intentar adivinar. Corré esto **una vez por cada código**, sin
`--report-id`, y el script prueba el código contra las solicitudes pendientes
hasta encontrar a cuál corresponde:

```powershell
python sync_sicop.py --confirmar --codigo Lw45ef
```

El código son 6-7 caracteres alfanuméricos y **distingue mayúsculas**
(`Lw45ef` no es lo mismo que `lw45ef`). No son solo dígitos.

Cuando lo acepta, el script espera a que SICOP termine de construir el reporte y
lo baja solo a `data\`. Eso puede tardar varios minutos por reporte.

Para ver en cualquier momento qué pediste y qué falta:

```powershell
python sync_sicop.py --pendientes
```

Si un reporte quedó a medias porque se cortó la espera, se retoma sin volver a
pedir el código:

```powershell
python sync_sicop.py --descargar --report-id 36749
```

### 7. Revisar sin tocar la base

```powershell
python sync_sicop.py --cargar --dry-run
```

Lee los archivos de `data\`, hace los joins, aplica el filtro ambiental e
imprime cuántos contratos encontró y en qué categorías — **sin escribir nada**.
Es el comando para confirmar que los archivos están bien antes de cargar.

### 8. Cargar y calcular el factor

```powershell
python sync_sicop.py --cargar --calcular-factor
```

Dos cosas en un comando:

- `--cargar` inserta los contratos ambientales en la tabla
  `contratos_ambientales`.
- `--calcular-factor` crea la vista `v_factor_inversion`, que es la que
  convierte esos contratos en un puntaje 0-100 por cantón.

**Los dos hacen falta.** Si cargás sin `--calcular-factor`, la vista no existe y
el backend deja el `factor_inversion` de todos los cantones en 0.

Al final imprime el ranking de cantones por factor de inversión.

### 9. Levantar el backend

```powershell
cd ..\..\backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Confirmá en http://localhost:8000/docs que responde.

### 10. Calcular el índice

En otra terminal:

```powershell
curl.exe -X POST http://localhost:8000/indice-viabilidad/recalcular
```

Devuelve `{"cantones_actualizados":84}`.

**Hay que repetir esto cada vez que se cargan datos nuevos de cualquier fuente
— el índice no se recalcula solo.**

---

## Cómo confirmar que los datos de SICOP están ahí

Ajustá el puerto si cambiaste `POSTGRES_PORT`.

```powershell
docker exec -it eco-inversion-db psql -U eco_inversion -d eco_inversion_cr -c "SELECT count(*) FROM contratos_ambientales;"
docker exec -it eco-inversion-db psql -U eco_inversion -d eco_inversion_cr -c "SELECT categoria_detectada, count(*), sum(monto) FROM contratos_ambientales GROUP BY categoria_detectada ORDER BY 2 DESC;"
docker exec -it eco-inversion-db psql -U eco_inversion -d eco_inversion_cr -c "SELECT nombre, contratos, monto_total, categorias, factor_inversion FROM v_factor_inversion WHERE contratos > 0 ORDER BY factor_inversion DESC LIMIT 10;"
docker exec -it eco-inversion-db psql -U eco_inversion -d eco_inversion_cr -c "SELECT * FROM sincronizaciones WHERE fuente_id = (SELECT fuente_id FROM fuentes WHERE codigo='SICOP') ORDER BY fecha_ejecucion DESC LIMIT 5;"
```

Toda corrida del ETL —incluidas las que fallan— queda registrada en
`sincronizaciones`. Ese es el mecanismo de trazabilidad del proyecto.

Por la API:

```powershell
curl.exe "http://localhost:8000/contratos-ambientales?canton_id=5"
curl.exe http://localhost:8000/indice-viabilidad
```

---

## Cómo se decide que un contrato es "ambiental"

No es machine learning: es una lista de palabras clave en 6 categorías que se
busca sobre la descripción del objeto contractual. `python sync_sicop.py
--criterio` imprime el criterio completo.

Se eligió así a propósito, para que el criterio se pueda leer entero y defender
en la exposición, y para que cuando se equivoque se vea exactamente por qué
palabra se equivocó. La contrapartida es imprecisión: hay falsos positivos y
falsos negativos, y están documentados en `docs/sicop.md`.

El detalle completo del criterio, de los pesos del factor y de la nota de
alcance (solo gobiernos locales) está en **`docs/sicop.md`**.

---

## Problemas conocidos y cómo resolverlos

| Síntoma | Causa | Solución |
|---|---|---|
| `La tabla cantones está vacía` | Se corrió SICOP antes que el paso 4 | Correr el paso 4 y repetir |
| El reporte nunca se construye, `--pendientes` dice "falta confirmar" | Se pidió sin `--correo`, así que SICOP nunca mandó el código | Volver a correr `--solicitar` **con** `--correo` |
| `Ninguna solicitud pendiente aceptó ese código` | Código incompleto o con mayúsculas cambiadas | Son 6-7 caracteres y distinguen mayúsculas. Copiar y pegar del correo, sin espacios |
| HTTP 500 al descargar | El reporte se confirmó pero todavía se está construyendo | Repetir `--descargar --report-id N`; el reporte no se pierde |
| `factor_inversion` en 0 para todos los cantones | Se cargó sin `--calcular-factor`, la vista no existe | `python sync_sicop.py --calcular-factor` y después `/recalcular` |
| El índice no cambia después de cargar datos | `/indice-viabilidad/recalcular` no se llamó | Paso 10 |
| Los montos se ven bajos | La vista solo suma contratos en colones | Es a propósito: los que quedaron en dólares sin tipo de cambio no se pueden sumar sin mentir. La vista los cuenta aparte en `contratos_otra_moneda` |
| El backend apunta a la base equivocada | `DATABASE_URL` y `POSTGRES_PORT` quedaron desalineados en el `.env` | Paso 2. El backend resuelve el `.env` desde la raíz del repo, no desde `backend\` |
| `error during connect ... dockerDesktopLinuxEngine` | Docker Desktop instalado pero cerrado | Abrirlo y esperar a que el engine arranque |

---

## Nota de alcance

El Factor de Inversión Municipal cuenta **solo contratos de gobiernos locales**
(municipalidades y concejos municipales de distrito). Una compra del ICE o del
AyA está domiciliada en su propio cantón, no donde ejecuta la obra, y contarla
distorsionaría el índice.

Se puede levantar esa restricción con `--todas-instituciones`, pero eso **cambia
el significado del factor** y hay que decirlo si se usa.

Los pesos internos del factor (50% monto, 30% cantidad, 20% diversidad) son una
**decisión del equipo**, no un estándar oficial. Es una inferencia construida
sobre los datos, no un dato en sí, y así hay que presentarla.
