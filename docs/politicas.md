# Políticas de contenedores (ítem 3.4)

Conftest evalúa con OPA/Rego los archivos que construyen o ejecutan
contenedores y bloquea el PR si alguno incumple. Las reglas están en
`politicas/`, sus pruebas en `politicas/politicas_test.rego` y las excepciones
en `politicas/datos/excepciones.yaml`.

## Reglas

| Id | Qué impide | Dónde se comprueba | Por qué ahí |
|---|---|---|---|
| P1 | Contenedores en modo privilegiado | Compose (`privileged: true`) y workflows (`--privileged`) | Es donde se decide cómo se ejecuta un contenedor; un Dockerfile no puede pedir modo privilegiado |
| U1 | Imágenes propias sin usuario no root explícito | `backend/Dockerfile` y `frontend/Dockerfile`: la etapa final debe declarar `USER` y el último no puede ser `root` ni `0` | La etapa final es la imagen que se publica en Docker Hub y se despliega |
| U2 | Forzar root al ejecutar | Compose (`user: root`, `user: 0`) | Sobrescribe el `USER` del Dockerfile y anularía U1 |

Archivos analizados: todo archivo versionado que se llame `Dockerfile*`,
`docker-compose*.yml` / `compose*.yml` o esté en `.github/workflows/`, salvo
`politicas/ejemplos/`. La lista sale de `git ls-files`, así que un archivo
nuevo de ese tipo queda cubierto sin cambiar la configuración.

Fuera del alcance: las imágenes de terceros que se usan sin `user` en Compose
(PostGIS, ZAP, Toxiproxy) conservan el usuario que define su proveedor. PostGIS
arranca como root y baja a `postgres` por diseño. No se despliegan junto a la
aplicación.

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

## Hallazgo real y excepción

La primera ejecución sobre el repositorio rechazó `docker-compose.seguridad.yml`
(U2): los servicios de Semgrep y Gitleaks usan `user: root` para escribir sus
reportes en la carpeta montada. Se registró la excepción EXC-01 en lugar de
cambiar la configuración de 2.3 y 3.2 al final de la entrega:

- Contenedores de un solo uso, código montado en solo lectura, sin puertos y
  sin despliegue.
- Responsable: Orlando. Aprobada por: Elein. Vence: 2026-12-15.
- Tratamiento previsto: ejecutar los escáneres con el UID del usuario que los
  lanza.

Cada excepción indica regla, archivo, servicio, justificación, responsable,
aprobación, vencimiento y enlace al registro único. Solo cubre esa regla en
ese archivo y servicio. Al vencer deja de aplicarse y la política vuelve a
fallar. Conftest la muestra como aviso (`WARN`) en cada ejecución. Con
`--sin-excepciones` se ve el rechazo original.

## Limitaciones

- No revisa capacidades sueltas (`cap_add: [SYS_ADMIN]`), `network_mode: host`
  ni montajes del socket de Docker, que también dan acceso al host.
- U1 confía en el Dockerfile: no comprueba el usuario de la imagen ya
  construida. Un `USER` con variables se rechaza porque no se puede verificar.
- Render ejecuta las imágenes publicadas sin Compose, así que en el ambiente
  desplegado la garantía viene de U1.
