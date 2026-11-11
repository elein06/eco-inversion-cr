# Análisis dinámico de seguridad (DAST) con ZAP (ítem 4.7)

## Qué se prueba

Un análisis DAST reproducible de la API en ejecución, con el **ZAP Automation
Framework**: rutas públicas y autenticadas, rastreo, análisis pasivo y
análisis activo acotado. Todo el análisis está en un plan versionado
(`dast/zap-plan.yaml`); no depende de configurar nada a mano en la interfaz de
ZAP.

DAST busca defectos genéricos (inyección, errores expuestos, cabeceras,
manejo de sesión). **No sustituye** las pruebas de autorización (ítem 4.5,
`backend/tests/api/test_autorizacion.py`): ZAP no sabe que el escenario de Ana
no debe verlo Beto.

```
ejecutar_dast.py ──► docker compose -p eco-dast (red interna "dast")
      │                 db  (PostGIS, tmpfs, sin puertos, datos ficticios)
      │                 backend (imagen de backend/, sin montar el código)
      │                 zap (zaproxy/zap-stable:2.16.1, solo ve la red "dast")
      │
      ├─ 1. levanta db + backend y espera /health/listo
      ├─ 2. crea las vistas v_factor_* con el SQL de los ETL
      ├─ 3. registra una cuenta ficticia por POST /auth/registro y le crea un escenario
      ├─ 4. ejecuta el plan de ZAP y guarda su salida
      ├─ 5. redacta tokens y contraseñas de los reportes
      ├─ 6. evalúa: APROBADO / FALLA / INCOMPLETO
      └─ 7. destruye el ambiente (docker compose down -v)
```

| Archivo | Función |
|---|---|
| `dast/zap-plan.yaml` | Plan de ZAP: contexto, autenticación, jobs y condición de fallo |
| `dast/docker-compose.yml` | Ambiente aislado (proyecto `eco-dast`, separado del de desarrollo) |
| `dast/datos_ficticios.sql` | Tres cantones ficticios (`DAST-0N`) e índice precalculado |
| `dast/ejecutar_dast.py` | Orquestador; solo biblioteca estándar de Python |
| `.github/workflows/dast.yml` | El mismo análisis en GitHub Actions |
| `dast/evidencia/` | Reportes de las corridas documentadas abajo |

## El plan (`dast/zap-plan.yaml`)

| Paso | Job de ZAP | Qué hace |
|---|---|---|
| Sesión | `requestor` ×2 | Con la cuenta de prueba, `/auth/yo` y el escenario propio (lectura, ranking, CSV) deben dar **200**; sin sesión, **401**. Si no, el análisis se detiene (ver abajo). |
| Rastreo | `openapi` | Importa `/openapi.json` de FastAPI: es el inventario real de una API JSON, con cuerpos de POST/PUT (42 URL). |
| Rastreo | `spider` ×2 | Uno sin sesión (rutas públicas) y otro con sesión (autenticadas). |
| Pasivo | `passiveScan-wait` | Revisa todas las respuestas registradas. |
| Activo | `activeScan` | Con la sesión de la cuenta de prueba: alcanza rutas públicas y privadas. |
| Evidencia | `report` ×2, `export` | `zap-reporte.html`, `zap-reporte.json`, `rutas-analizadas.txt`. |
| Fallo | `exitStatus` | Código 1 con alertas de riesgo Medio o Alto; 2 con alertas Bajas. |

### Autenticación

La API usa JWT en `Authorization: Bearer` (no cookies). ZAP hace el login JSON
real (`POST /auth/login`), toma `access_token` de la respuesta y lo envía en
cada solicitud (`sessionManagement: headers`, `{%json:access_token%}`). Cada 30
solicitudes consulta `/auth/yo`; si responde "Se requiere iniciar sesión",
vuelve a iniciarla.

La cuenta es de rol **usuario**, creada por el flujo real de registro con una
contraseña aleatoria en cada corrida. El rol admin no se analiza (ver
Limitaciones).

### Cómo se acota el análisis activo

- **Por tecnología:** el contexto excluye las que el proyecto no usa (MySQL,
  SQL Server, Oracle, MongoDB, Windows, PHP, Java, IIS, Tomcat, etc.). ZAP
  omite sus cargas específicas y conserva las que aplican (inyección SQL de
  PostgreSQL, inyección de comandos de Linux, XSS, path traversal…).
- **Por tiempo:** 2 min por regla y 20 min en total. Si llega a los 20 min,
  quedaron reglas sin ejecutar y el resultado es **INCOMPLETO**.
- **Intensidad** media y 4 hilos.
- **Alcance:** solo `DAST_TARGET.*`; ZAP no sale de la red interna.

## Condiciones de fallo

| Resultado | Cuándo | Código de salida |
|---|---|---|
| **APROBADO** | El plan terminó, la sesión funcionó, el análisis activo terminó antes del límite, hay rutas registradas y no hay alertas de riesgo Medio ni Alto. Las alertas Bajas se reportan. | 0 |
| **FALLA** | Alguna alerta de riesgo **Medio** o **Alto**, o ZAP terminó con error. | 1 |
| **INCOMPLETO** | La sesión no funcionó, la API no respondió, ZAP no generó el reporte, no hay rutas registradas, el análisis activo no terminó o llegó al límite de tiempo. | 1 |

Un análisis incompleto **nunca** se reporta como aprobado.

Hay un detalle de ZAP que obligó a una comprobación propia: cuando un
`requestor` recibe un código distinto del esperado, ZAP lo registra solo como
**advertencia** (`Difference in response code values…`) y sigue. El análisis
correría sin sesión, sin probar las rutas privadas, y podía terminar
"aprobado". `ejecutar_dast.py` vigila la salida, detiene ZAP en cuanto aparece
ese mensaje y marca la corrida como INCOMPLETO (corrida **c**).

Una alerta Media o Alta que se decida aceptar temporalmente se excluye con un
job `alertFilter` en el plan, referenciando su entrada en el registro único de
hallazgos y excepciones (responsable, aprobación y fecha de revisión). Hoy no
hay ninguna.

## Decisiones del ambiente

| Decisión | Por qué |
|---|---|
| `LOGIN_MAX_INTENTOS=100000` **solo** en el ambiente DAST | El análisis activo envía contraseñas inválidas a `/auth/login` con la cuenta de ZAP (536 intentos fallidos en la corrida **b**). Con el límite normal (5) la cuenta quedaría bloqueada y el resto del análisis correría sin sesión. El bloqueo lo prueban las pruebas de API (F1). |
| Vistas `v_factor_*` creadas desde el SQL de los ETL | No están en `db/schema.sql`. Sin ellas, las cuatro rutas de factores responden antes de tocar sus parámetros y ZAP no prueba sus consultas (corrida **a**). El script extrae las constantes `SQL_FACTOR_*` de los módulos del ETL con `ast`, sin importarlos ni copiar el SQL. |
| Tokens y contraseña redactados en los reportes | La alerta 10112 cita la respuesta de `/auth/login`, que trae el `access_token`. Aunque es de un ambiente desechable, no se guardan tokens en artefactos ni en Git (Gitleaks los detectaría). |
| `JWT_SECRET` aleatorio en cada corrida | No hay secretos fijos en el repositorio. |
| Base en `tmpfs`, sin puertos publicados | Nada queda entre corridas; la API solo se publica en `127.0.0.1` para crear la cuenta. |

## Cómo ejecutarlo

Requisitos: Docker Desktop y Python 3.10 o superior. Desde la raíz del
repositorio (PowerShell o Bash):

```bash
python dast/ejecutar_dast.py                         # análisis completo (~12 min)
python dast/ejecutar_dast.py --demo-sesion-invalida  # demostración: debe terminar INCOMPLETO
```

La evidencia queda en `dast/resultados/<fecha>/` (ignorada por Git):
`resumen.md`, `zap-reporte.html`, `zap-reporte.json`, `rutas-analizadas.txt`,
`zap-salida.txt` y `api-log.txt`. `dast/resultados/ultimo-resumen.md` es una
copia del último resumen.

Sin Docker, contra una API ya levantada sobre una base de pruebas con
`db/*.sql` y `dast/datos_ficticios.sql` cargados, y `LOGIN_MAX_INTENTOS` alto:

```bash
python dast/ejecutar_dast.py --objetivo http://127.0.0.1:8000 \
    --base postgresql://usuario:clave@127.0.0.1/base_dast \
    --zap /ruta/a/ZAP_2.16.1/zap.sh --log-api /ruta/al/log-de-uvicorn.txt
```

**En CI:** `.github/workflows/dast.yml` lo ejecuta en cada PR hacia
`development` o `main` que toque `backend/`, `db/`, `dast/` o el propio
workflow, y a mano (`workflow_dispatch`). Construye la API del commit del PR,
publica el resumen en la página de la ejecución y conserva `dast/resultados/`
como artefacto `dast-<sha>` durante 30 días. El job falla con FALLA o
INCOMPLETO.

## Resultados

Corridas del 2026-11-09. Las corridas **a** a **c** se ejecutaron contra el
commit `1bceb32` en el workspace Linux de Claude **sin Docker** (modo
`--objetivo`, ZAP 2.16.1 y PostgreSQL 16 + PostGIS 3 nativos), porque ese
entorno no tiene acceso a Docker Hub. La corrida **d** es el camino normal:
`python dast/ejecutar_dast.py` con Docker Desktop en Windows, sobre el commit
del ítem (base `development`) más el cambio de nombre del servicio `api` a
`backend` (ver abajo), que se versionó a continuación. El código de la API es el mismo en todas.
Archivos en `dast/evidencia/`: `resumen.md`, `zap-reporte.json`,
`zap-salida.txt` y, en **b** y **d**, las rutas y un extracto del log de la API. El reporte HTML no se versiona (sus enlaces
`http://127.0.0.1` activan la regla `plaintext-http-link` de Semgrep en CI);
se genera en cada corrida local y queda en el artefacto de GitHub Actions.

| Corrida | Qué demuestra | Resultado |
|---|---|---|
| **a** exploratoria | Primera versión del plan, sin vistas ni filtro de tecnologías. Llegó al límite de 15 min. Ver `NOTA.md`. | Sería INCOMPLETO con las reglas actuales |
| **b** completa | Plan actual. Sesión verificada; 34 rutas (9 con sesión); análisis activo de 10 min 28 s. | **APROBADO** (1 alerta Baja) |
| **c** sesión inválida | `--demo-sesion-invalida`: ZAP recibe una contraseña incorrecta, `/auth/yo` da 401 en vez de 200 y el script detiene ZAP en segundos. | **INCOMPLETO**, código 1 |
| **d** Docker | Ambiente aislado completo con `dast/docker-compose.yml` e imagen oficial de ZAP. Sesión verificada; 34 rutas (9 con sesión); análisis activo de 8 min 37 s; 9,6 min en total. | **APROBADO** (2 alertas Bajas) |
| **e** GitHub Actions | Workflow `DAST` en el PR #21, commit `c8f4435`, runner `ubuntu-24.04`: [ejecución 42719554136](https://github.com/elein06/eco-inversion-cr/actions/runs/42719554136). Reportes en el artefacto `dast-c8f44359f248346bd420f9aad51cd87e5a3d0807` (30 días). Job de 6 min 26 s. | **APROBADO** (job en verde) |

La primera ejecución con Docker en Windows terminó INCOMPLETO antes de llegar a
ZAP: Python enviaba el SQL de las vistas a `psql` en cp1252 y la `ó` de los
comentarios del ETL llegaba como byte inválido. Se corrigió enviándolo siempre
como UTF-8. El script lo reportó como incompleto, no como aprobado.

Al versionar la evidencia de Docker, el job Seguridad del PR falló: Gitleaks
(regla `generic-api-key`) marcó 52 coincidencias en los reportes porque el
servicio se llamaba `api` y cada URL empezaba con `http://api:8000/…`, que la
regla lee como `api: <clave>`. Era un falso positivo, pero en vez de excluir la
evidencia del análisis de secretos se renombró el servicio a `backend`, se
quitó ese commit de la rama y se repitió la corrida **d**.

Alertas de ZAP en las corridas **b** y **d** (instancias de **b** / **d**):

| Riesgo | Id | Alerta | Instancias |
|---|---|---|---|
| Bajo | 10021 | X-Content-Type-Options Header Missing | 28 / 28 |
| Bajo | 10116 | ZAP is Out of Date | — / 1 |
| Informativo | 10111 | Authentication Request Identified | 3 / 3 |
| Informativo | 10112 | Session Management Response Identified | 68 / 4 |
| Informativo | 10104 | User Agent Fuzzer | 108 / 108 |

La 10116 solo aparece en **d** porque la imagen de ZAP está fijada en 2.16.1
para que el análisis sea reproducible; actualizarla queda a cargo de Renovate
(ítem 7.6).

En la corrida **d** la API respondió a 19 866 solicitudes y registró 45
accesos sin sesión, 30 accesos denegados, 520 logins fallidos y 175 registros
rechazados (`api-log-extracto.txt`; en **b**: 19 575 solicitudes y 536 logins
fallidos). En las dos hubo exactamente 32 respuestas 500, todas de
H-DAST-02, con cuerpo genérico y sin trazas.

## Hallazgos

Para pasar al registro único del proyecto. Ninguno está corregido todavía.

| Id | Riesgo | Hallazgo | Evidencia | Tratamiento propuesto |
|---|---|---|---|---|
| **H-DAST-01** | Bajo | Ninguna respuesta de la API envía `X-Content-Type-Options: nosniff` (alerta ZAP 10021). | Corridas **b** y **d**, `zap-reporte.json` | Middleware que agregue `X-Content-Type-Options: nosniff` (y `Cache-Control: no-store` en respuestas con sesión). Una prueba de API que lo verifique. |
| **H-DAST-02** | Bajo | Un byte NUL (`%00`) en `canton` o `provincia` de `/ambiental/factor`, `/inversion/factor`, `/infraestructura/factor` y `/seguridad/factor` produce un **500** no controlado (`ValueError: A string literal cannot contain NUL`). La consulta está parametrizada: no es inyección, es validación de entrada. ZAP **no** lo alertó (el cuerpo es genérico); se encontró revisando el log de la API. | Corridas **b** y **d**, `api-log-extracto.txt` (32 respuestas 500 en cada una) | Rechazar NUL con 422 en esos parámetros (validación de FastAPI o un manejador global de `ValueError`). Prueba de regresión con `?canton=a%00b`. |
| **H-DAST-03** | Bajo | `/ambiental/factor` responde **500** si la vista `v_factor_ambiental` no existe; las otras tres rutas de factores responden 503 con un mensaje claro (`_exigir_vista`). Alertas ZAP 90022 y 10023. | Corrida **a**, `zap-reporte.json` | Aplicar la misma comprobación de vista en `routers/ambiental.py`. |

## Limitaciones

- El modo Docker se validó en Windows (corrida **d**) y en GitHub Actions
  (corrida **e**). Los reportes de **e** viven solo en el artefacto, que
  GitHub borra a los 30 días: descargarlo antes de la evaluación si se quiere
  conservar.
- Las imágenes `zaproxy/zap-stable:2.16.1` y `postgis/postgis:16-3.4` están
  fijadas por etiqueta, no por digest. Para fijarlas:
  `docker pull zaproxy/zap-stable:2.16.1` y
  `docker inspect --format "{{index .RepoDigests 0}}" zaproxy/zap-stable:2.16.1`.
- Solo se analiza con el rol **usuario**. `POST /indice-viabilidad/recalcular`
  se prueba sin permiso (403) pero no como admin.
- La importación OpenAPI deja los parámetros de ruta vacíos
  (`/escenarios//ranking`). Las rutas con un id real (`/escenarios/1/…`) las
  aporta el job `requestor`, solo con GET.
- El análisis activo usa intensidad media y excluye tecnologías: no es una
  prueba de penetración exhaustiva.
- ZAP no detecta fallas de lógica ni de autorización entre cuentas (IDOR):
  eso lo cubren las pruebas de API.
- Hay 500 que ZAP no reporta como alerta si el cuerpo no expone detalles
  (H-DAST-02). Por eso el script conserva el log de la API como evidencia.
- ZAP inicia sesión con mucha frecuencia (2 740 logins en la corrida **b**,
  2 693 en **d**).
  No afecta el resultado, pero llenaría de ruido una alerta de logins
  (ítem 7.3) si el análisis se corriera contra el ambiente desplegado.
