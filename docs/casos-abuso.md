# Casos límite, abuso y omisiones (ítem 1.6)

En este ítem usé IA para que me propusiera casos raros o maliciosos que el
sistema podría no manejar bien. Después revisé cada caso en el código y en las
pruebas que ya tiene el equipo, y el equipo decidió cuáles se aceptan.
**Nada se agregó al proyecto solo porque la IA lo dijo.**

## ¿Cómo se hizo?

1. Le pedí a un asistente de IA (Claude) que propusiera casos límite,
   escenarios de abuso y omisiones, usando como base:
   - las amenazas del modelo ([amenazas.md](amenazas.md)),
   - las reglas de [autenticacion.md](autenticacion.md),
   - el código del backend (`auth.py`, `routers/auth.py`, `routers/escenarios.py`,
     `routers/indice.py`, `crear_usuario.py`, `indice.py`, `pesos.py`).
2. La IA propuso 17 casos y 6 dudas el 08/11/2026.
3. Revisé cada caso contra el código y contra las pruebas de `backend/tests/`.
   Uno se descartó porque no se puede reproducir (CA-14) y otro estaba mal
   descrito (CA-10). Se agregó CA-05b.
4. Las dudas se registraron como Issues en GitHub (#15 a #20), con un responsable.
5. Karina (@KarinaMD16), responsable de las reglas de autenticación, revisó los casos
   contra el código y las pruebas, respondió las dudas en los Issues y en la revisión
   del [PR #28](https://github.com/elein06/eco-inversion-cr/pull/28) (11/11/2026), y
   cada caso quedó con su decisión.

## ¿Qué significan las etiquetas?

| Etiqueta | Significa |
|---|---|
| **R** Regla aprobada | Ya está acordada en un documento aprobado (por ejemplo `autenticacion.md`) |
| **O** Observado en el código | Es lo que el código hace hoy; lo verificamos leyendo el código |
| **S** Sugerencia pendiente | Idea de la IA que todavía no se ha comprobado |

## A) Casos que ya están cubiertos por una prueba del equipo

| ID | Tipo | ¿Qué pasaría? | ¿Qué hace el código hoy? | Etiqueta | Prueba existente | Relación |
|---|---|---|---|---|---|---|
| CA-04 | Límite | Registrar o iniciar sesión con el email en MAYÚSCULAS | Se convierte a minúsculas; es la misma cuenta | O | `test_registro_email_duplicado_sin_distinguir_mayusculas` | F1 |
| CA-05 | Límite | Contraseña de menos de 12 caracteres | Responde 422 | R + O | `test_registro_password_corta` | F1 |
| CA-06 | Abuso | Una cuenta desactivada sigue usando su token | Se revisa `activo` en cada petición; responde 401 | R + O | `test_cuenta_desactivada_no_puede_usar_su_token` | T-08 |
| CA-09 | Límite | El admin pide el escenario de otro usuario | Responde 404 | R + O (la regla la confirmó D1) | `test_escenario_de_otro_404_sin_exponer_datos` | F3 |
| CA-10 | Límite | Pesos con `NaN`, `Infinity` o `True` | Se rechazan. Una suma de 0.999 **sí** se acepta por la tolerancia de ±0.001 | O | `test_peso_fuera_de_rango_o_no_numerico`, `test_suma_dentro_de_la_tolerancia` | F3 |
| CA-11 | Límite | Escenario sin cantones | El ranking usa todos los cantones | O | `test_ranking_sin_cantones_usa_todos` | F3 |
| CA-13 | Abuso | Un nombre con `=HYPERLINK(...)` llega al CSV y se ejecuta al abrirlo en Excel | `_celda_segura` lo neutraliza | O | `test_csv_neutraliza_formulas` | T-02 |
| CA-15 | Abuso | Probar ids de escenarios ajenos uno por uno | Siempre 404 y cada intento queda registrado como evento | O | `test_acceso_ajeno_queda_registrado` | T-07, T-09 |
| CA-17 | Límite | `JWT_SECRET` con menos de 32 caracteres | La API no arranca | O | `test_secreto_corto_impide_arrancar` | T-03 |

## B) Casos que se pueden probar y nadie ha probado todavía

| ID | Tipo | ¿Qué pasaría? | ¿Cómo se prueba? | Resultado esperado según el código | Etiqueta | Relación | Decisión | Validó |
|---|---|---|---|---|---|---|---|---|
| CA-01 | Abuso | Una cuenta crea muchísimos escenarios y llena la base | Crear, por ejemplo, 500 escenarios con el mismo token | Todos responden 201: no hay límite | O | T-06 | Riesgo aceptado; se retoma con T-06 (D6, [#20](https://github.com/elein06/eco-inversion-cr/issues/20)) | Karina |
| CA-02 | Abuso | Registro masivo de cuentas automáticas | Registrar 50 cuentas seguidas | Todas responden 201: no hay límite ni CAPTCHA | O + R | T-04, T-06 | Aceptado como limitación | Karina |
| CA-03 | Abuso | `crear_usuario` con el email de alguien que ya existe | Registrar un usuario normal y luego correr `crear_usuario --email <ese> --rol admin` | El usuario pasa a admin y se le cambia la contraseña (`ON CONFLICT DO UPDATE`) | O | T-03 | Intencional, se mantiene (D2, [#16](https://github.com/elein06/eco-inversion-cr/issues/16)) | Karina |
| CA-05b | Límite | Contraseña de 129 caracteres | Registrarse con 129 caracteres | Responde 422 (máximo 128) | R + O | F1 | Pendiente de prueba | Karina |
| CA-12 | Límite | Un cantón sin datos en un factor recibe 0 y parece "malo" | Recalcular el índice con un cantón sin datos de un factor | Ese factor queda en 0 (`indice.py`) | O | F2, T-02 | Se mantiene en 0, limitación conocida (D5) | Karina |
| CA-16 | Omisión | Alguien registra el email de otra persona | Registrar `x@correo.com` y luego intentar registrarlo otra vez | La primera vez 201 y la segunda 409: la persona real queda fuera | O | T-10 | Aceptado como limitación | Karina |

## C) Omisiones (no son pruebas; se documentan)

| ID | ¿Qué falta? | ¿Cómo se comprobó? | Etiqueta | Decisión | Validó |
|---|---|---|---|---|---|
| CA-07 | No se puede cambiar ni recuperar la contraseña | No existe ninguna ruta para eso en `routers/auth.py`; `autenticacion.md` lo lista como limitación | R | Limitación aceptada, fuera del alcance de esta entrega (D3, [#17](https://github.com/elein06/eco-inversion-cr/issues/17)) | Karina |
| CA-08 | No hay forma de desactivar una cuenta desde la aplicación | El campo `activo` existe en la base, pero ninguna ruta lo cambia | O | Limitación aceptada: se desactiva por SQL y el efecto es inmediato (D3, [#17](https://github.com/elein06/eco-inversion-cr/issues/17)) | Karina |

## D) Casos descartados

| ID | ¿Qué proponía la IA? | ¿Por qué se descartó? |
|---|---|---|
| CA-14 | El admin recalcula el índice mientras el ETL está cargando y se mezclan datos viejos y nuevos | No se puede reproducir de forma confiable: depende de que dos procesos coincidan en el tiempo |

## Errores de la IA que se corrigieron

Al revisar el código, encontramos que la IA se equivocó en 4 cosas:

| La IA dijo | El código dice | Qué se hizo |
|---|---|---|
| En T-03: "el rol va dentro del token" | El rol se lee de la base en cada petición (`auth.py`) | Se corrigió la descripción de T-03 (la prioridad no cambió) |
| En T-08: "aunque haya cambiado su contraseña" | No existe cambio de contraseña, y desactivar la cuenta sí corta el token | Se corrigió la descripción de T-08 |
| "El CSV no protege contra fórmulas" | `_celda_segura` ya lo hace (`routers/escenarios.py`) | Se descartó; quedó como CA-13 (ya cubierto) |
| En CA-10: "pesos que suman 0.999 se rechazan" | Se aceptan a propósito por la tolerancia de ±0.001 (`pesos.py`) | Se corrigió la descripción de CA-10 |

Esto muestra por qué cada propuesta de la IA se revisa antes de usarla.

## Dudas y decisiones

La IA **no** decidió estas respuestas: cada una tiene un responsable, y la decisión
quedó escrita en GitHub.

| # | Pregunta | Casos | Responsable | Issue | Decisión |
|---|---|---|---|---|---|
| D1 | ¿El admin puede ver escenarios de otros usuarios? | CA-09 | @KarinaMD16 | [#15](https://github.com/elein06/eco-inversion-cr/issues/15) | Se mantiene: el admin recibe 404, igual que cualquier usuario ajeno |
| D2 | ¿Es intencional que `crear_usuario` sobrescriba una cuenta que ya existe? | CA-03 | @KarinaMD16 | [#16](https://github.com/elein06/eco-inversion-cr/issues/16) | Intencional: sirve para promover o restablecer cuentas y solo la corre quien tiene acceso a la base |
| D3 | ¿Cambiar/recuperar contraseña y desactivar cuentas entran en el alcance, o quedan como limitación? | CA-07, CA-08 | @KarinaMD16 | [#17](https://github.com/elein06/eco-inversion-cr/issues/17) | Limitación aceptada, fuera del alcance de esta entrega |
| D4 | ¿Un escenario sin cantones debe usar todos los cantones? | CA-11 | @KarinaMD16 | [#18](https://github.com/elein06/eco-inversion-cr/issues/18) | Comportamiento esperado: sin cantones se evalúa todo el país |
| D5 | ¿Un cantón sin datos debe valer 0 o mostrarse como "sin datos"? | CA-12 | @KarinaMD16 | [#19](https://github.com/elein06/eco-inversion-cr/issues/19) | Se mantiene en 0, limitación conocida (decidido en la revisión del PR #28) |
| D6 | ¿Debe haber un límite de escenarios por usuario? | CA-01 | @KarinaMD16 | [#20](https://github.com/elein06/eco-inversion-cr/issues/20) | Riesgo aceptado; se retoma junto con T-06 (límite de peticiones) |

## Qué se incorporó al proyecto

- **Modelo de amenazas (ítem 1.3):** se corrigieron las descripciones de T-03 y T-08
  con lo que se encontró al revisar los errores de la IA. Entró en el
  [PR #14](https://github.com/elein06/eco-inversion-cr/pull/14).
- **Reglas confirmadas:** D1 (el admin no ve escenarios ajenos), D2 (la CLI sobrescribe
  a propósito) y D4 (sin cantones = todo el país). Por eso CA-09 pasó de "R pendiente"
  a "R + O".
- **Limitaciones aceptadas:** D3, D5, CA-02 y CA-16. Quedan registradas aquí y en sus
  Issues para que el equipo sepa que son decisiones, no olvidos.
- **Riesgo aceptado ligado a una amenaza:** D6 y CA-01 se retoman junto con T-06.
- **Prueba pendiente:** CA-05b (contraseña de 129 caracteres → 422).
- **Pendientes en `docs/autenticacion.md`** (responsable: Karina): quitar la nota
  "Decisión pendiente de validar" (D1) y documentar que `crear_usuario` sobrescribe
  contraseña, rol y estado (D2).