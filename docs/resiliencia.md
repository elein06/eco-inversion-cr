# Experimento de resiliencia con Toxiproxy (ítem 4.10)

## Qué se prueba

**Dependencia crítica:** PostgreSQL. Todos los flujos de la API (login,
escenarios, índice, zonas) dependen de ella. Si la base se pone lenta o se
cae, la API debe responder con un error claro y a tiempo, no dejar datos a
medias y recuperarse sola cuando la base vuelve.

```
pytest / Artillery ──► API (FastAPI) ──► Toxiproxy :15432 ──► PostgreSQL :5432
                                               ▲
                                   API de control :8474
                          (meter latencia, congelar, cortar)
```

Las verificaciones de consistencia usan una conexión **directa** a la base
(sin pasar por el proxy), para observar el estado real mientras la API falla.

**Límites que ya tenía la API** (`backend/app/database.py`, `config.py`):
`DB_CONNECT_TIMEOUT=5` s para conectar, `DB_STATEMENT_TIMEOUT_MS=15000` por
consulta, y `main.py` convierte cualquier `OperationalError` en un 503 con
`Retry-After: 5` y mensaje genérico.

## Escenarios, comportamiento esperado y recuperación

| ID | Fallo (toxic) | Duración | Comportamiento esperado | Recuperación |
|---|---|---|---|---|
| R1 | `latency` 300 ms | una solicitud | 200, más lenta pero < 5 s | quitar toxic |
| R2 | `latency` 10 000 ms | una solicitud | 503 limpio en ≤ ~5 s (connect timeout) | quitar toxic |
| R3 | proxy deshabilitado | una solicitud | 503 inmediato; `/health` sigue en 200; el login da 503 y **no** suma intentos fallidos | habilitar proxy |
| R4 | proxy deshabilitado durante `POST /escenarios` | una solicitud | 503 y ninguna fila nueva; al volver, el mismo pedido crea exactamente una | habilitar proxy |
| R5 | corte y restauración | una solicitud | sin reiniciar, `/health/listo` vuelve a 200 en < 1 s | automática |
| R6 | `timeout` 0 (red congelada) con una solicitud **ya conectada** | hasta 7 s | 503 en ≤ statement_timeout + 2 s; nunca colgada | quitar toxic |
| C1 | carga de 5 sol/s; corte de los 20 a los 40 s | 60 s | 200 → 503 rápidos sin timeouts → 200 | automática |

R1–R6 están en `backend/tests/api/resiliencia/test_toxiproxy.py`; C1 en
`resiliencia/experimento_carga.py` + `resiliencia/artillery.yml`. Las pruebas
restauran el proxy al terminar aunque fallen.

## Hallazgo (R6) y corrección

**Hipótesis inicial:** con los timeouts existentes, ninguna solicitud puede
quedar colgada.

**Resultado:** falso. R6 falló de forma repetible: con la red congelada
después de conectar, la solicitud quedó colgada más de 60 s (sin límite).

**Causa:** `statement_timeout` lo aplica **el servidor**. En R6 el servidor ya
respondió; la respuesta se pierde en la red y psycopg2 espera para siempre.
`connect_timeout` solo cubre la conexión. Además cada solicitud colgada
ocupa uno de los hilos del servidor: con suficientes, la API entera deja de
responder.

**Corrección:** límite de espera del lado del cliente en
`backend/app/database.py` (`_esperar_con_limite`, registrado con
`psycopg2.extensions.set_wait_callback`). Cada operación tiene un plazo:
`DB_CONNECT_TIMEOUT` al conectar y `DB_STATEMENT_TIMEOUT_MS + 2 s` después.
Al agotarse se lanza `BaseSinRespuesta` (un `OperationalError`), que termina
en el mismo 503 de siempre. R6 es ahora la prueba de regresión.

## Cómo reproducirlo

Requisitos: Docker Desktop, el entorno de `backend/` con
`requirements-dev.txt` y, para C1, Node.js. Comandos para PowerShell, desde la
raíz del repositorio:

```powershell
# 1. Base de pruebas + Toxiproxy (crear la base _test solo la primera vez)
docker compose -f docker-compose.yml -f docker-compose.resiliencia.yml up -d db toxiproxy
docker compose exec db createdb -U eco_inversion eco_inversion_test

# 2. Pruebas R1–R6 (puerto y contraseña salen del .env: POSTGRES_PORT, POSTGRES_PASSWORD)
cd backend
$pw = (Select-String -Path ..\.env -Pattern '^POSTGRES_PASSWORD=(.*)$').Matches[0].Groups[1].Value
$port = (Select-String -Path ..\.env -Pattern '^POSTGRES_PORT=(.*)$').Matches[0].Groups[1].Value
$env:TEST_DATABASE_URL="postgresql://eco_inversion:${pw}@127.0.0.1:${port}/eco_inversion_test"
$env:TOXIPROXY_URL="http://127.0.0.1:8474"
pytest -m resiliencia -v

# 3. Carga C1: en una terminal, la API conectada A TRAVÉS del proxy (15432)
$env:DATABASE_URL="postgresql://eco_inversion:${pw}@127.0.0.1:15432/eco_inversion_test"
uvicorn app.main:app --host 127.0.0.1 --port 8000
#    y en otra terminal, desde la raíz del repositorio:
python resiliencia/experimento_carga.py
```

Se usa `127.0.0.1` y no `localhost` a propósito: en Windows `localhost` intenta
primero IPv6, el proxy solo escucha en IPv4 y cada conexión pierde ~2 s antes
de reintentar. En la primera corrida en Windows eso sumó 2 s a R2, R3 y R5 y
las hizo fallar por tiempo; no era un defecto de la API sino del ambiente.

El paso 2 siembra la base `_test` con datos ficticios que luego usa el paso 3.
Sin `TOXIPROXY_URL` las pruebas aparecen como *skipped*: un experimento que no
corrió no cuenta como aprobado. C1 deja su reporte, la línea de tiempo y un
resumen en `resiliencia/resultados/`. La telemetría de la API son los logs de
uvicorn: cada 503 registra `base_no_disponible request_id=... ruta=...`, el
mismo `X-Request-ID` que recibe el cliente.

## Resultados

| ID | Antes de la corrección | Después |
|---|---|---|
| R1–R5 | aprobadas | aprobadas |
| R6 | **falla**: colgada > 7 s (> 60 s sin límite) | aprobada: 503 en ~4 s |
| C1 | — | 0–20 s: 200 · 20–40 s: 100 % 503 en ≤ 4 ms, 0 timeouts · desde 40 s: 200 |

La evidencia de cada corrida (salida de pytest, reportes de C1 y logs) está
enlazada en el registro de hallazgos del proyecto.

## Limitaciones

- Solo se prueba PostgreSQL. Las fuentes externas del ETL (SNIT, SICOP, OIJ,
  OSM) no forman parte de la API en ejecución.
- R6 corta una solicitud con una sola consulta; las de varias consultas
  quedan protegidas por la misma función, pero no se probaron por separado.
- La corrección acota la espera a 17 s con los valores por defecto. No evita
  que, con mucha carga y la red congelada, se ocupen todos los hilos durante
  esos segundos. Un pool con límite o un circuit breaker serían el paso
  siguiente.
- Al congelar la red, la sesión del servidor puede quedar abierta hasta que
  TCP note la caída. El experimento no lo mide.
- Corre solo en el ambiente de pruebas, contra una base cuyo nombre termina
  en `_test` (el conftest lo exige). La API de Toxiproxy no tiene
  autenticación; por eso se publica solo en `127.0.0.1`.
