# Políticas de contenedores (ítem 3.4)

Conftest evalúa con OPA/Rego los archivos que construyen o ejecutan
contenedores. Si alguno incumple, el check "Políticas (Conftest)" falla, y como
es obligatorio en la protección de `development` y `main`, el PR no se puede
fusionar. Las reglas están en
`politicas/`, sus pruebas en `politicas/politicas_test.rego` y las excepciones
en `politicas/datos/excepciones.yaml`.

## Reglas

| Id | Qué impide | Dónde se comprueba | Por qué ahí |
|---|---|---|---|
| P1 | Contenedores en modo privilegiado | Compose (`privileged: true`) y workflows (`--privileged`) | Es donde se decide cómo se ejecuta un contenedor; un Dockerfile no puede pedir modo privilegiado |
| U1 | Imágenes propias sin usuario no root explícito | `backend/Dockerfile` y `frontend/Dockerfile`: la etapa final debe declarar `USER` y el último no puede ser `root` ni `0` | La etapa final es la imagen que se publica en Docker Hub y se despliega |
| U2 | Forzar root al ejecutar | Compose: `user: root`, `user: 0` o un `user` con variables, como `${USUARIO:-root}`, que no se puede comprobar | Sobrescribe el `USER` del Dockerfile y anularía U1 |
| U3 (aviso) | No bloquea: señala imágenes de terceros sin `user` | Compose: servicio con `image`, sin `build` y sin `user` | Esas imágenes pueden correr como root por defecto sin declararlo, y U2 no lo ve |

Archivos analizados: todo archivo versionado que se llame `Dockerfile*`,
`docker-compose*.yml` / `compose*.yml` o esté en `.github/workflows/`, salvo
`politicas/ejemplos/`. La lista sale de `git ls-files`, así que un archivo
nuevo de ese tipo queda cubierto sin cambiar la configuración.

Imágenes de terceros: las que se usan sin `user` en Compose conservan el
usuario que define su proveedor, que puede ser root. U3 las muestra como aviso
(`WARN`) en cada ejecución para que alguien las revise, pero no bloquea:
algunas necesitan arrancar como root y bajan de privilegios solas (PostGIS
arranca como root y pasa a `postgres`). No se despliegan junto a la aplicación.

### U3: aviso que salió de la revisión

Al corregir EXC-01 en el PR #24, Orlando encontró que OSV-Scanner también
corría como root aunque U2 no lo marcaba: sus servicios no declaraban `user`.
Era un punto ciego de U2. En lugar de dejarlo solo como limitación, se agregó
U3, con 3 pruebas (25 en total). Hoy avisa por PostGIS (`docker-compose.yml` y
`dast/`), ZAP y Toxiproxy; OSV-Scanner deja de aparecer cuando se fusiona el
PR #24, que le declara `user: "1001:1001"`.

## Cómo ejecutarlo

Desde la raíz, en PowerShell o Bash. Usa `conftest` si está instalado; si no,
la imagen `openpolicyagent/conftest` en Docker:

```bash
python politicas/verificar.py                    # pruebas de las reglas + repositorio
python politicas/verificar.py --demo             # caso permitido y caso rechazado
python politicas/verificar.py --sin-excepciones  # el repositorio sin excepciones
```

Los resultados quedan en `reportes/politicas/` (ignorada por Git). En CI,
[.github/workflows/politicas.yml](../.github/workflows/politicas.yml) corre en
cada PR hacia `development` o `main` y guarda esos reportes como artefacto
`politicas-<sha>`.

Códigos de salida: 0 cumple; 1 una política rechaza o la demostración no dio
el resultado esperado; 2 Conftest no pudo ejecutarse, que cuenta como análisis
incompleto y no como aprobado.

## Demostración

`politicas/ejemplos/permitido/` pasa las tres reglas: la etapa final usa
`USER app`, Compose usa `user: "1000:1000"` y no hay modo privilegiado.

`politicas/ejemplos/rechazado/` falla con las tres:

```
FAIL - [P1] politicas/ejemplos/rechazado/docker-compose.yml: el servicio 'api' usa privileged: true.
FAIL - [U1] politicas/ejemplos/rechazado/Dockerfile: la etapa final termina con USER root.
FAIL - [U2] politicas/ejemplos/rechazado/docker-compose.yml: el servicio 'worker' se ejecuta con user: root.
```

Los ejemplos están en `.semgrepignore` porque el rechazado es inseguro a
propósito y haría fallar el análisis de Semgrep.

## Hallazgo real: de excepción a corrección

La primera ejecución sobre el repositorio rechazó `docker-compose.seguridad.yml`
(U2): los servicios de Semgrep y Gitleaks usaban `user: root` para escribir sus
reportes en la carpeta montada. El hallazgo siguió este camino:

1. **Excepción temporal EXC-01** (PR #22, issue #23): cubría solo `semgrep`,
   `gitleaks-historial` y `gitleaks-archivos`, con vencimiento el 2026-12-15.
   Se justificó porque son contenedores de un solo uso, con el código en solo
   lectura, sin puertos y sin despliegue. Orlando, responsable del archivo, no
   la aprobó como solución: prefirió corregir el problema.
2. **Corrección** (PR #24, Orlando): los cinco servicios de escaneo corren con
   el UID fijo `1001:1001`, incluido OSV-Scanner, que corría como root sin
   declararlo (de ahí salió el aviso U3).
3. **Retiro de la excepción** (este PR): `excepciones: []`. El check de
   Políticas de este PR confirma que, sin la excepción, el repositorio no
   tiene ningún FAIL. El issue #23 queda cerrado.

El #22 se fusionó con EXC-01 todavía vigente porque el #24 no podía fusionarse
sin el check obligatorio de Políticas, y ese workflow venía en el #22. Diana la
aprobó solo como excepción temporal con este plan de retiro.

Cada excepción indica regla, archivo, servicios, justificación, responsable,
aprobación, vencimiento y enlace al registro único. Solo cubre esa regla, en
ese archivo, para los servicios que nombra uno por uno: no hay comodín. `-`
indica una regla de archivo completo (U1 en un Dockerfile, P1 en un
workflow). `vence` es el último día válido, hasta las 23:59:59 hora de Costa
Rica. Al vencer deja de aplicarse y la política vuelve a
fallar. Conftest la muestra como aviso (`WARN`) en cada ejecución. Con
`--sin-excepciones` se ve el rechazo original.

## Revisión del PR #22

La revisión asistida por IA de Diana (ítem 2.6) encontró siete puntos. Se
corrigieron así:

| Hallazgo | Cambio |
|---|---|
| H-01 `servicio: "*"` cubría cualquier servicio del archivo | Lista explícita `servicios`, sin comodín. Prueba con un servicio nuevo `prueba-h01` |
| H-02 U2 aceptaba `user: "${USUARIO:-root}"` | U2 rechaza un `user` con variables, igual que U1. El tratamiento de EXC-01 ya no propone variables |
| H-03 EXC-01 sin enlace al registro | Enlazada con el issue #23 (cerrado al retirarla) |
| H-04 `vence` se leía como 00:00 UTC | Vigente hasta las 23:59:59 de Costa Rica, con pruebas del límite |
| H-05 Pruebas faltantes | 6 pruebas nuevas: 22 en total |
| H-06 ¿El check bloquea? | "Políticas (Conftest)" agregado como check obligatorio en `development` y `main` |
| H-07 ¿Quién aprueba EXC-01? | Orlando no la aprobó: corrigió los escáneres en el #24. Diana la aprobó solo como temporal para destrabar el orden de los PR, y se eliminó en el PR "Retira EXC-01" |

## Limitaciones

- No revisa capacidades sueltas (`cap_add: [SYS_ADMIN]`), `network_mode: host`
  ni montajes del socket de Docker, que también dan acceso al host.
- U1 confía en el Dockerfile: no comprueba el usuario de la imagen ya
  construida. Un `USER` con variables se rechaza porque no se puede verificar.
- Render ejecuta las imágenes publicadas sin Compose, así que en el ambiente
  desplegado la garantía viene de U1.
- U3 solo avisa: no sabe con qué usuario arranca cada imagen de terceros (eso
  depende de la imagen, no del archivo), así que una persona tiene que revisar
  cada aviso.
