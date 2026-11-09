# Modelo de amenazas (STRIDE)

Este documento corresponde al ítem 1.3. Usé **OWASP Threat Dragon** para dibujar
cómo se mueven los datos en la aplicación y buscar qué podría salir mal en cada parte.

Me enfoqué en los flujos críticos que están en [autenticacion.md](autenticacion.md):

- **F1:** registro e inicio de sesión
- **F2:** recalcular el índice de viabilidad (solo el admin)
- **F3:** escenarios privados de cada usuario

También agregué el **ETL**, porque es lo que carga los datos que después usa el índice.

## Archivos

| Archivo | Para qué sirve |
|---|---|
| [eco-inversion.json](threat-model/eco-inversion.json) | El modelo. Se abre con Threat Dragon. |
| [diagrama-flujos.png](threat-model/diagrama-flujos.png) | Imagen del diagrama. |
| [reporte-amenazas.pdf](threat-model/reporte-amenazas.pdf) | Reporte que genera Threat Dragon con las 10 amenazas. |

![Diagrama de flujos](threat-model/diagrama-flujos.png)

En el diagrama, lo que está en **rojo** es donde encontramos amenazas.

## ¿Qué es STRIDE?

Es una lista de 6 tipos de ataque. A cada amenaza le pusimos la letra que le corresponde:

| Letra | Significa | Qué rompe |
|---|---|---|
| **S** | Spoofing (suplantar) | Hacerse pasar por otra persona |
| **T** | Tampering (alterar) | Cambiar datos sin permiso |
| **R** | Repudiation (negar) | Negar que uno hizo algo y que no se pueda probar |
| **I** | Information disclosure (filtrar) | Ver información que no le toca |
| **D** | Denial of service (bloquear) | Dejar el sistema o una cuenta sin servicio |
| **E** | Elevation of privilege (subir permisos) | Hacer cosas de admin sin serlo |

## Fronteras de confianza

Son las líneas punteadas del diagrama. Marcan dónde los datos pasan de un lugar
en el que no confiamos a uno en el que sí. Ahí es donde más hay que revisar.

| Frontera | Qué separa |
|---|---|
| **B1** Internet / navegador → servidor | El navegador del usuario (no lo controlamos) del backend |
| **B2** Servidor → base de datos | El backend de la base de datos, que tiene lo más importante |
| **B3** Datos de terceros → ETL | Los archivos y páginas externas de los que sacamos datos |

## ¿Cómo decidimos la prioridad?

A cada amenaza le dimos dos notas del 1 al 3:

- **Probabilidad (P):** qué tan fácil o común es que pase.
- **Impacto (I):** qué tan grave sería si pasa.

Después las multiplicamos:

| P × I | Prioridad |
|---|---|
| 7 a 9 | Alta |
| 4 a 6 | Media |
| 1 a 3 | Baja |

## Amenazas encontradas

| ID | ¿Qué podría pasar? | STRIDE | ¿Dónde? | P × I | Prioridad |
|---|---|---|---|---|---|
| T-01 | La base de datos tiene el puerto 5432 abierto y la contraseña por defecto es `changeme`. Alguien podría entrar directo. | I | PostgreSQL | 3 × 3 = 9 | **Alta** |
| T-02 | Alguien cambia un archivo de SICOP/OIJ o una fuente externa y el ETL carga datos falsos. | T | Lee xlsx / csv | 2 × 3 = 6 | Media |
| T-03 | Si se filtra la clave secreta del JWT, alguien puede crear un token falso, incluso de admin. | S | Backend | 2 × 3 = 6 | Media |
| T-04 | Prueban correos y contraseñas filtrados de otras páginas (credential stuffing). Solo hay bloqueo por cuenta, no por IP. | S | Backend | 3 × 2 = 6 | Media |
| T-05 | Alguien falla el login a propósito con el correo de otra persona para bloquearle la cuenta. | D | Backend | 3 × 2 = 6 | Media |
| T-06 | No hay límite de peticiones; muchas peticiones a los mapas podrían poner lento o botar el backend. | D | Backend | 2 × 2 = 4 | Media |
| T-07 | Los logs se pueden borrar o perder, y después no se puede probar quién hizo algo. | R | Logs de seguridad | 2 × 2 = 4 | Media |
| T-08 | Si roban un token, sirve hasta que vence (30 min), aunque el usuario cierre sesión. | S | Backend | 2 × 2 = 4 | Media |
| T-09 | Un usuario cambia el id en la URL para ver escenarios de otro (IDOR). Ya está controlado: responde 404. | I | Peticiones API | 1 × 3 = 3 | Baja |
| T-10 | Al registrarse, la API dice si un correo ya existe, así se puede saber quién tiene cuenta. | I | Registro | 3 × 1 = 3 | Baja |

Cada amenaza tiene su explicación completa (recurso, impacto y por qué esa
prioridad) dentro del modelo de Threat Dragon y en el PDF.

### Algunas notas

- **La más importante es T-01**, porque se puede atacar sin pasar por la aplicación.
- **T-03 también es E**, porque con un token falso de admin se pueden hacer cosas de admin.
  Threat Dragon solo deja escoger una letra, por eso quedó como S.
- **T-10 ayuda a T-04 y T-05:** primero averiguan qué correos existen y luego los atacan.
- **T-09 quedó en Baja** porque el código ya revisa que el escenario sea del usuario
  (`backend/app/routers/escenarios.py`). La dejamos para que se vea que sí la revisamos.
- Las soluciones de cada amenaza van en el ítem **1.4**.

## Uso de IA

Usé un asistente de IA (Claude) para que me propusiera los flujos del diagrama,
las fronteras y una primera lista de amenazas. La IA también agregó las flechas y
las fronteras al archivo del modelo. Yo puse los elementos en Threat Dragon,
revisé y acomodé las flechas y fronteras, revisé cada amenaza contra el código
y contra `autenticacion.md`, las ingresé en Threat Dragon y les puse la prioridad
con la regla P × I.
