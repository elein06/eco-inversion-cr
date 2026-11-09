# Revisión de código asistida por IA (ítem 2.6)

En este ítem usé un asistente de IA (Claude) para revisar un Pull Request y buscar
defectos, problemas de seguridad y pruebas que faltan. **La IA no decide nada:** cada
hallazgo se deja como comentario en la línea exacta del código y la persona dueña
del código decide si lo corrige, si no aplica o si se deja en un Issue.

La IA tampoco aprueba el PR. Eso lo siguen haciendo el CI (checks *Backend* y
*Frontend*) y la revisión de otro integrante del equipo.

## Qué PR reviso

| Revisión | PR | Autor/a | Estado |
|---|---|---|---|
| **Principal** (asignada por el equipo) | PR de Elein | @elein06 | Pendiente: Elein todavía no abre su PR |
| Extra (práctica del proceso) | [#10 Autenticación, roles y escenarios privados](https://github.com/elein06/eco-inversion-cr/pull/10) | @KarinaMD16 | Hecha: 7 hallazgos |

El equipo decidió que a mí me toca revisar el PR de Elein. Mientras ella lo abre,
probé el proceso completo con el PR #10 de Karina, porque tiene el código de los
flujos críticos F1 y F3 (login y escenarios privados).

## Cómo lo hice (el proceso)

1. **Darle contexto a la IA.** No le pedí solo "revisa este código". Le di el PR, los
   requisitos (`docs/autenticacion.md`) y los riesgos (`docs/amenazas.md`, ítem 1.3),
   para que revisara contra lo que el sistema **debe** hacer.
2. **Revisar lo que propuso la IA.** Leí cada hallazgo contra el código. Si algo
   dependía de una regla del equipo (por ejemplo, permisos), no se asumió la
   respuesta: quedó como **DUDA**.
3. **Comprobar en la API.** Levanté el proyecto con Docker y probé en Swagger el
   hallazgo más importante (H-01) para ver si era real.
4. **Comentar en el PR.** Cada hallazgo quedó como comentario en la línea exacta
   (pestaña *Files changed*), con ubicación, justificación, comprobación sugerida y
   la persona que tiene que decidir.
5. **Otra persona decide.** El autor del PR responde en el mismo hilo:
   ✅ lo corrige, ❌ no aplica (con la razón) o 📌 se deja en un Issue.
6. **Resumen.** Las decisiones se pasan a la tabla de este documento.

### Prompt que se usa

Este es el prompt que le di a la IA. Para otro PR solo cambian las partes de
"CAMBIO A REVISAR", "REQUISITOS" y "RIESGOS".

```text
Actúa como revisor de código de seguridad para el repositorio eco-inversion-cr.

CAMBIO A REVISAR
- PR #10 "Autenticación, roles y escenarios privados con pruebas" (commit da38b30), comparado contra su rama base.

REQUISITOS (cómo debe comportarse)
- docs/autenticacion.md: flujos F1 (autenticación), F2 (recalcular índice, solo admin) y F3 (escenarios privados), roles, reglas de acceso, criterios de aceptación y controles.

RIESGOS (qué puede salir mal)
- Modelo de amenazas del ítem 1.3: docs/amenazas.md, amenazas T-01 a T-10.

QUÉ BUSCAR
1. Defectos: el código no cumple un requisito o un criterio de aceptación.
2. Problemas de seguridad: relacionados con las amenazas T-01 a T-10 u otros que encuentres.
3. Pruebas faltantes: comportamientos importantes sin prueba en backend/tests.

FORMATO DE CADA HALLAZGO
- ID (H-01, H-02…), título corto y tipo (defecto / seguridad / prueba faltante)
- Ubicación: archivo y línea
- Justificación: qué requisito o amenaza (T-xx) afecta y por qué
- Comprobación sugerida: cómo verificar si el hallazgo es real
- ¿Hay una prueba existente que lo cubra? (sí/no y cuál)
- Severidad: alta / media / baja

REGLAS
- Máximo 8 hallazgos, los más importantes.
- Si algo depende de una decisión del equipo (permisos o comportamiento esperado), no asumas la respuesta: anótalo como DUDA con la persona que debería responderla.
- No apruebes el cambio. Tu revisión no reemplaza el CI ni la revisión humana; la decisión sobre cada hallazgo la toma otro integrante.
```

---

## Revisión principal: PR de Elein

*Pendiente.* Cuando Elein abra su PR se sigue el mismo proceso y se llena esta parte.

| ID | Hallazgo | Tipo | Ubicación | Severidad | Comentario | Decisión de Elein |
|---|---|---|---|---|---|---|
| | | | | | | |

---

## Revisión extra: PR #10 (Karina)

- **PR:** [#10](https://github.com/elein06/eco-inversion-cr/pull/10), commit `da38b30`.
- **Quién decide:** @KarinaMD16, autora del PR y dueña del requisito.
- **Nota:** el PR #10 ya estaba aceptado (merge) cuando lo revisé. Por eso lo que se
  decida corregir va en un PR nuevo o en un Issue, no en el mismo PR.

| ID | Hallazgo | Tipo | Ubicación | Severidad | Comentario | Decisión de Karina |
|---|---|---|---|---|---|---|
| H-01 | El login revela si una cuenta existe: la que existe se bloquea (429) y la que no existe siempre da 401 | Seguridad | `backend/app/routers/auth.py:116` | Media | [ver](https://github.com/elein06/eco-inversion-cr/pull/10#discussion_r4515852342) | Pendiente |
| H-02 | No hay pruebas de que el contador de fallos se reinicie ni de que el bloqueo venza | Prueba faltante | `backend/app/routers/auth.py:121` | Media | [ver](https://github.com/elein06/eco-inversion-cr/pull/10#discussion_r4515860051) | Pendiente |
| H-03 | DUDA: ¿el admin puede ver escenarios de otros usuarios? | Duda (permisos) | `docs/autenticacion.md:38` | — | [ver](https://github.com/elein06/eco-inversion-cr/pull/10#discussion_r4515932306) · Issue [#15](https://github.com/elein06/eco-inversion-cr/issues/15) | Pendiente |
| H-04 | DUDA: volver a correr `crear_usuario` cambia el rol y reactiva la cuenta | Duda (permisos) | `backend/app/crear_usuario.py:45` | — | [ver](https://github.com/elein06/eco-inversion-cr/pull/10#discussion_r4515956167) · Issue [#16](https://github.com/elein06/eco-inversion-cr/issues/16) | Pendiente |
| H-05 | DUDA: no hay límite de escenarios por usuario | Duda / seguridad | `backend/app/routers/escenarios.py:167` | Baja | [ver](https://github.com/elein06/eco-inversion-cr/pull/10#discussion_r4515964046) · Issue [#20](https://github.com/elein06/eco-inversion-cr/issues/20) | Pendiente |
| H-06 | Si el escenario se borra a mitad de una actualización, responde 500 en vez de 404 | Defecto | `backend/app/routers/escenarios.py:231` | Baja | [ver](https://github.com/elein06/eco-inversion-cr/pull/10#discussion_r4515969014) | Pendiente |
| H-07 | Detrás de un proxy, todos los eventos de seguridad guardarían la IP del proxy | Seguridad | `backend/app/eventos.py:52` | Baja | [ver](https://github.com/elein06/eco-inversion-cr/pull/10#discussion_r4516008970) | Pendiente |

H-03, H-04 y H-05 también salieron en el ítem 1.6 (casos de abuso), por eso tienen
su Issue. Son la misma duda vista desde el código y desde las reglas.

### Comprobación de H-01 en la API

Lo probé yo misma en Swagger (`http://localhost:8000/docs`) el 9-nov-2026:

1. Creé una cuenta de prueba → `201`.
   ![Registro](revision-ia/h01-1-registro.png)
2. Hice 6 logins con contraseña incorrecta en esa cuenta → el sexto respondió
   `429` (cuenta bloqueada).
   ![Cuenta existente: 429](revision-ia/h01-2-existe-429.png)
3. Hice 25 logins con un correo que **no** existe → siempre respondió `401`.
   ![Cuenta inexistente: 401](revision-ia/h01-3-no-existe-401.png)

**Resultado:** el hallazgo es real. Con 6 intentos se puede saber si un correo tiene
cuenta, aunque `docs/autenticacion.md` dice que el login no lo revela. Los eventos
de seguridad del backend quedaron en [h01-logs.txt](revision-ia/h01-logs.txt)
(request-id `7fc55b72…` para el 429 y `cfdba2ed…` para el 401). En el log no
aparecen contraseñas ni tokens, y el correo de la cuenta inexistente sale como hash.

## Qué hizo la IA y qué hice yo

| La IA | Yo |
|---|---|
| Propuso los hallazgos a partir del prompt | Escribí el prompt con los requisitos y las amenazas |
| Sugirió la ubicación, la justificación y cómo comprobarlos | Revisé cada hallazgo contra el código antes de publicarlo |
| Ayudó a redactar los comentarios | Hice la prueba de H-01 en Swagger y guardé la evidencia |
| — | Publiqué los comentarios en el PR y le asigné la decisión a la persona responsable |

La decisión final de cada hallazgo **no** es mía ni de la IA: es del autor del PR.
