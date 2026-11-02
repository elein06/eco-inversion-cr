# Autenticación, roles y escenarios privados

Hasta la v0.1 la API era 100 % pública y la única operación de escritura
(`POST /indice-viabilidad/recalcular`) no pedía sesión. Esta versión agrega
usuarios, roles y un recurso con dueño (los **escenarios**), que es la base
para los flujos críticos, las reglas de acceso y las pruebas de autorización
del proyecto final de Desarrollo Seguro.

## Flujos críticos

| Id | Flujo | Por qué es crítico |
|---|---|---|
| **F1** | Registro e inicio de sesión (`/auth/*`) | Maneja credenciales. Un fallo permite suplantar usuarios o administradores. |
| **F2** | Recalcular el índice oficial (`POST /indice-viabilidad/recalcular`) | Integridad: el índice es lo que ven los inversionistas. Si cualquiera puede recalcularlo (o alterar sus entradas) se publica una recomendación falsa. |
| **F3** | Escenarios privados (`/escenarios/*`), incluida la exportación CSV | Confidencialidad y propiedad: los pesos y cantones que evalúa una ONG o inversionista son información estratégica suya. |

## Roles

| Rol | Cómo se obtiene |
|---|---|
| **anónimo** | Sin sesión. |
| **usuario** | `POST /auth/registro`. Siempre crea este rol; enviar `"rol"` en el cuerpo es un 422. |
| **admin** | Solo por línea de comandos, con acceso a la base: `python -m app.crear_usuario --email ... --rol admin`. |

## Reglas de acceso (actor → recurso → acción → condición)

| Actor | Recurso | Acción | Condición |
|---|---|---|---|
| anónimo, usuario, admin | Datos públicos (`/zonas`, `/indice-viabilidad`, factores, capas, `/health`) | Leer | Siempre (datos OSINT ya públicos y agregados). |
| anónimo | Cualquier ruta protegida | Cualquiera | **401** + `WWW-Authenticate: Bearer`. |
| anónimo | Cuenta propia | Registrarse / iniciar sesión | Contraseña de 12 a 128 caracteres. Bloqueo de 15 min tras 5 fallos seguidos (**429**). |
| usuario, admin | Su sesión (`/auth/yo`) | Leer | Token vigente **y** cuenta activa (se relee de la base en cada solicitud). |
| usuario, admin | Escenario **propio** | Crear, leer, modificar, borrar, ranking, exportar CSV | `escenarios.usuario_id = usuario en sesión`. |
| usuario, admin | Escenario **ajeno** | Cualquiera | **404** (igual que si no existiera, para no revelar ids) + evento `acceso_denegado`. |
| usuario | Índice oficial | Recalcular | **403** + evento `acceso_denegado`. El índice no cambia. |
| admin | Índice oficial | Recalcular | Permitido; queda evento `recalcular_indice` con el id del admin. |

> **Decisión pendiente de validar por el responsable del requisito:** el admin
> **no** puede leer escenarios de otros usuarios. Se eligió así porque su rol
> es operar el índice, no auditar el trabajo privado de los usuarios. Si el
> equipo decide lo contrario, hay que cambiar `_obtener_propio` en
> `backend/app/routers/escenarios.py` **y** las pruebas parametrizadas con
> `"admin"` en `tests/api/test_autorizacion.py` dentro del mismo PR.

## Criterios de aceptación (Dado / Cuando / Entonces)

**F1 — Inicio de sesión**
- *Éxito:* Dado un usuario activo, cuando envía email y contraseña correctos, entonces recibe un token que vence en 30 min y `/auth/yo` devuelve sus datos.
- *Error:* Dado un email inexistente o una contraseña incorrecta, cuando intenta entrar, entonces recibe 401 con **el mismo mensaje** en ambos casos.
- *Uso indebido:* Dado un atacante que prueba contraseñas, cuando acumula 5 fallos seguidos, entonces la cuenta queda bloqueada 15 min (429 aun con la contraseña correcta) y cada intento queda registrado sin la contraseña.
- *Uso indebido:* Dado alguien que se registra enviando `"rol": "admin"`, entonces recibe 422 y no se crea ninguna cuenta.

**F2 — Recalcular el índice**
- *Éxito:* Dado un admin con sesión, cuando llama a `/recalcular`, entonces se actualizan los 84 cantones y queda un evento con su id.
- *Error:* Dado un usuario normal, cuando llama a `/recalcular`, entonces recibe 403 y `fecha_calculo` no cambia.
- *Uso indebido:* Dado un token alterado (otro `sub`, `alg: none`, otra firma), entonces recibe 401. Dado un admin degradado a usuario, su token vigente deja de servir para recalcular.

**F3 — Escenarios**
- *Éxito:* Dada Ana con sesión, cuando crea un escenario con pesos que suman 1, entonces puede ver su ranking (índice con sus pesos) y exportarlo como CSV.
- *Error:* Pesos que no suman 1 (±0.001), fuera de 0–1, cantones repetidos o inexistentes, o más de 84 cantones → 422.
- *Uso indebido:* Dado Beto (o un admin), cuando pide, modifica, borra, rankea o exporta el escenario de Ana, entonces recibe 404, no ve ningún dato y el escenario queda igual. Enviar `usuario_id` en el cuerpo es un 422.

## Controles implementados

| Control | Dónde |
|---|---|
| Contraseñas con argon2id; verificación contra un hash de relleno si la cuenta no existe (mismo tiempo de respuesta) | `app/auth.py` |
| JWT HS256 con lista cerrada de algoritmos, `exp`/`iat`/`sub` obligatorios, secreto ≥ 32 caracteres o la API no arranca | `app/auth.py`, `app/main.py` |
| Rol y estado se releen de la base en cada solicitud (no se confía en el token) | `auth.usuario_actual` |
| Bloqueo por intentos fallidos | `routers/auth.py` |
| `extra="forbid"` en todas las entradas (sin asignación masiva) | `routers/auth.py`, `routers/escenarios.py` |
| Propiedad comprobada en la aplicación **y** repetida en el `WHERE` del UPDATE/DELETE | `routers/escenarios.py` |
| CSV sin inyección de fórmulas (`=`, `+`, `-`, `@` se prefijan con `'`) y `Cache-Control: no-store` | `routers/escenarios.py` |
| Eventos de seguridad en JSON (logger `eco.seguridad`) con `request_id`, sin email, contraseña ni token | `app/eventos.py` |
| `X-Request-ID` en cada respuesta para correlacionar logs | `app/main.py` |
| Timeouts hacia PostgreSQL y respuesta 503 limpia si la base no responde | `app/database.py`, `app/main.py` |
| `/health` (proceso vivo) y `/health/listo` (base accesible) | `app/main.py` |

### Eventos de seguridad que se registran

`registro`, `login` (`exito` / `fallido` / `bloqueado`), `acceso_sin_sesion`,
`token_invalido`, `token_usuario_inactivo`, `acceso_denegado`
(`requiere_admin` / `no_es_dueno`), `recalcular_indice`, `exportacion`.
Para una cuenta inexistente se guarda solo una huella SHA-256 truncada del
email (`cuenta`), suficiente para ver ataques contra la misma cuenta.

## Limitaciones conocidas

- El token vive en el cliente hasta que vence; no hay lista de revocación ni
  "cerrar sesión" del lado del servidor. Mitigación: duración corta (30 min) y
  la cuenta desactivada deja de funcionar de inmediato.
- `/auth/registro` responde 409 si el email ya existe, lo que permite saber
  si una cuenta existe. Se aceptó por usabilidad; el login no lo revela.
- El bloqueo por intentos es por cuenta, no por IP: un atacante puede bloquear
  la cuenta de otra persona a propósito (denegación de servicio dirigida).
- No hay límite de solicitudes global (rate limiting) ni recuperación de
  contraseña.
- El frontend todavía no tiene pantallas de login ni de escenarios.

## Cómo probarlo

```bash
# Base nueva: compose carga db/02_usuarios_escenarios.sql solo.
# Base existente: aplicar la migración una vez
docker compose exec -T db psql -U eco_inversion -d eco_inversion_cr < db/02_usuarios_escenarios.sql
# En PowerShell (no acepta '<'):
# cmd /c "docker compose exec -T db psql -U eco_inversion -d eco_inversion_cr < db\02_usuarios_escenarios.sql"

# Crear el primer admin (pide la contraseña)
cd backend && python -m app.crear_usuario --email admin@ejemplo.cr --rol admin
```

Pruebas automáticas (ver README, sección "Pruebas"):

- `tests/unit/` — reglas de pesos y tokens, sin base de datos.
- `tests/api/` — F1, F2 y F3 contra un PostgreSQL+PostGIS de pruebas: accesos
  permitidos y denegados por rol, por propiedad y sin sesión, comprobando que
  los rechazos no expongan ni modifiquen datos.
