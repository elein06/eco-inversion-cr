# Actualizaciones y reescaneos periódicos (ítem 7.6)

Hay dos mecanismos que se complementan:

| Mecanismo | Qué hace | Dónde |
|---|---|---|
| **Renovate** | Propone por PR las versiones nuevas de dependencias, imágenes base y acciones de GitHub | `.github/renovate.json5` |
| **Reescaneo programado** | Vuelve a analizar todos los días lo que **está desplegado** y lleva los resultados al registro de hallazgos | `.github/workflows/reescaneo.yml` |

Renovate evita quedarse atrás. El reescaneo detecta las vulnerabilidades que
se publican **después** de desplegar. En ese caso el código no cambió y el CI
(3.2) no vuelve a correr, así que solo el reescaneo puede verlas.

## Renovate

### Qué actualiza

| Tipo | Archivos | Cómo |
|---|---|---|
| Python | `backend/requirements*.lock` | Regenera los lockfiles con `uv pip compile`, con el mismo comando de su encabezado (hashes incluidos) |
| npm | `frontend/package.json` y `package-lock.json`, `resiliencia/` | Sube el rango y el lockfile |
| Imágenes base | `backend/Dockerfile`, `frontend/Dockerfile` | Nueva versión o nuevo digest, siempre fijado por digest |
| Herramientas | `docker-compose.seguridad.yml`, `docker-compose.resiliencia.yml`, `dast/docker-compose.yml` | Un PR agrupado («herramientas de análisis») |
| Acciones de GitHub | `.github/workflows/*.yml` | Nuevo SHA con su comentario de versión, en un PR agrupado |

Fuera del alcance: `etl/` (no se despliega y sus `requirements.txt` no fijan
versiones) y `politicas/ejemplos/` (casos de prueba fijos del 3.4).

### Decisiones

- **Rama `development`:** todos los PR van ahí, como los del equipo.
- **Sin automerge.** Un PR de Renovate necesita los mismos checks que
  cualquier otro (CI, Seguridad, Políticas y DAST si toca el backend) y la
  aprobación de un revisor. Renovate no tiene ningún permiso especial.
- **Espera de 3 días** (`minimumReleaseAge`) antes de proponer una versión
  recién publicada, para que una versión maliciosa o defectuosa normalmente ya
  esté retirada. Las correcciones de vulnerabilidades no esperan.
- **Alertas de vulnerabilidades con OSV** (`osvVulnerabilityAlerts`): es la
  misma base que usa OSV-Scanner en CI. Esos PR llevan la etiqueta `seguridad`.
- **Mantenimiento semanal de lockfiles** (lunes antes de las 6 a. m.):
  actualiza las dependencias transitivas dentro de los rangos declarados.
- **Límites:** Python se queda en 3.12, porque cambiarlo es una decisión del
  equipo (CI, `uv` y el Dockerfile la fijan). PostGIS no recibe versiones
  mayores, porque requieren migrar datos. Hay como máximo 5 PR abiertos y 2
  por hora.
- **Panel de dependencias:** Renovate mantiene un issue «Panel de dependencias
  (Renovate)» con todo lo pendiente. Desde ahí se puede forzar un PR o
  reintentarlo.

### Cambio en los lockfiles de Python

Renovate no aceptaba el encabezado original de los lockfiles: `-c`, `-o` y
`--python-version 3.12` sin `=`. Los dos lockfiles se regeneraron con la forma
larga, y **solo cambió la línea del comando**: ninguna versión ni ningún hash.

```bash
cd backend
uv pip compile requirements.txt --universal --python-version=3.12 --generate-hashes --output-file=requirements.lock
uv pip compile requirements-dev.txt --constraint=requirements.lock --universal --python-version=3.12 --generate-hashes --output-file=requirements-dev.lock
```

La configuración se validó con `renovate-config-validator` y con una corrida
local de Renovate (`--platform=local --dry-run`). Esa corrida detectó 141
dependencias en 20 archivos de 6 gestores: docker-compose, dockerfile,
github-actions, npm, pip-compile y pip_requirements.

### Activarlo (una vez, la dueña del repositorio)

1. Instalar la app [Renovate](https://github.com/apps/renovate) solo en
   `elein06/eco-inversion-cr`.
2. Renovate lee su configuración de la **rama por defecto**. Hoy es `main`,
   así que `.github/renovate.json5` tiene que estar en `main`. Hay dos formas:
   - cambiar la rama por defecto a `development` (Settings → General). Esto
     además activa el cron del reescaneo, que también se lee de la rama por
     defecto; o
   - llevar este cambio también a `main`.

   Si al instalarla Renovate no encuentra la configuración, abre un PR
   «Configure Renovate» con una configuración propia. Ese PR se cierra sin
   fusionar.
3. En unos minutos aparecen el panel de dependencias y los primeros PR.

### Demostración: un PR real

1. Esperar el primer PR de Renovate hacia `development`, o forzarlo desde el
   panel de dependencias marcando su casilla.
2. En el PR se ve que corren CI (Backend, Frontend, Seguridad), Políticas y,
   si toca `backend/**`, DAST. El botón de fusionar queda bloqueado hasta que
   pasen los checks y apruebe un revisor.
3. Al fusionarlo, el workflow de publicación (5.5) publica y despliega la
   imagen nueva por digest, y el siguiente reescaneo la analiza.

Evidencia: enlace al PR, ejecución de los checks y aprobación del revisor.

## Reescaneo programado

### Qué analiza

El reescaneo analiza **lo que corre en Render**, no lo último de la rama:

1. **Versión desplegada.** Lee el commit que informan la API (`/health`) y el
   frontend (`/version.txt`), las mismas comprobaciones que usa el despliegue
   (6.1). Con ese commit resuelve en Docker Hub el digest de la imagen
   `sha-<commit>` que publicó el workflow de publicación.
2. **Dependencias.** Hace checkout de ese commit y corre OSV-Scanner sobre los
   lockfiles de producción: `backend/requirements.lock` y
   `frontend/package-lock.json`. Servicio `osv-reescaneo` de
   `docker-compose.seguridad.yml`.
3. **Imágenes.** Descarga `imagen@sha256:…` de backend y frontend y la
   analiza con `osv-scanner scan image`, que revisa los paquetes del sistema
   (Debian o Alpine) y los de la aplicación. Servicio `osv-imagen`.

Se usa OSV-Scanner, con la misma imagen fijada por digest que en CI (3.2). Así
no se agrega otra herramienta ni otra base de vulnerabilidades.

### Cuándo corre

| Disparador | Modo |
|---|---|
| Todos los días a las 6:17 a. m. de Costa Rica (cron) | Registra |
| Manual (*Run workflow*) | Registra |
| Al fusionar en `development` un cambio del reescaneo | Registra (sirve de demostración) |
| PR que modifica el reescaneo | **Simulación**: analiza, pero no escribe en el registro |

GitHub solo ejecuta el cron y el botón *Run workflow* desde la rama por
defecto. Mientras esa rama sea `main`, ver el paso 2 de «Activarlo».

### Cómo se convierten los resultados en hallazgos

El registro único son los issues de GitHub, igual que el issue #23 del 3.4.
Lo hace `.github/scripts/hallazgos_reescaneo.py`.

- **Un hallazgo por paquete vulnerable**, con todas sus vulnerabilidades en
  una tabla dentro del issue. La identidad es origen + ecosistema + paquete, y
  queda en un comentario oculto del issue para que la corrida siguiente lo
  encuentre sin duplicarlo. Los alias de una misma vulnerabilidad (GHSA, PYSEC,
  CVE) son una sola fila. Se agrupa por paquete porque así se corrige:
  actualizar `curl` corrige todos sus CVE a la vez. La primera versión abría un
  issue por CVE y creó unos 80 en la primera corrida; la siguiente corrida los
  cierra como *not planned* con un enlace al issue agrupado que los reemplaza.
- **Qué se registra:** un paquete se registra si alguna de sus
  vulnerabilidades tiene versión corregida publicada o CVSS de 7.0 o más. El
  resto (sobre todo paquetes del sistema sin corrección y de severidad baja)
  queda como informativo en el resumen de la ejecución.
- **Ritmo:** GitHub limita la creación rápida de issues y comentarios. Las
  escrituras van espaciadas 1 s y, si GitHub responde con ese límite, se
  espera 60 s y se reintenta.

| Situación | Qué hace |
|---|---|
| Paquete nuevo y registrable | Crea un issue con etiquetas `hallazgo`, `reescaneo`, `pendiente-investigacion` y `severidad:<nivel>` |
| Ya registrado y abierto | Actualiza la descripción (tabla, versión, última detección) y la severidad. Solo comenta si cambió el conjunto de vulnerabilidades |
| Cerrado y reaparece | Lo reabre con un comentario: la corrección no se sostuvo |
| Cerrado como `falso-positivo` o `riesgo-aceptado` y sigue apareciendo | No lo toca; solo comenta si aparecen vulnerabilidades nuevas |
| Abierto y ya no aparece | Comenta una vez y agrega `no-detectado`. **No lo cierra:** cerrarlo requiere enlazar el PR correctivo y esta ejecución como comprobación (7.7) |

Cada issue trae los campos del registro único (7.5): origen, versión
afectada (commit y digest), evidencia (ejecución y artefacto), severidad
justificada (CVSS máximo según OSV), responsable (se asigna al investigar),
estado (pendiente de investigación) y tratamiento propuesto (versión que lo
corrige, o excepción temporal si no hay corrección).

### Qué hace fallar el workflow

Una vulnerabilidad **no** lo hace fallar, porque se registra como hallazgo.
Sí falla, y la corrida no cuenta como reescaneo hecho, cuando:

- la API no informa un commit válido después de 5 minutos;
- la imagen `sha-<commit>` no está en Docker Hub;
- OSV-Scanner termina con un código distinto de 0 o 1, o no deja reporte;
- la autoprueba del registro falla o la API de GitHub rechaza un cambio.

La autoprueba (`.github/scripts/test_hallazgos_reescaneo.py`) comprueba sin red
que un reporte produce los hallazgos esperados y que se crean, actualizan,
reabren y marcan los issues correctos. Se corre antes de tocar el registro:

```bash
python .github/scripts/test_hallazgos_reescaneo.py -v
```

### Evidencia que deja cada ejecución

- Resumen de la ejecución: commit y digests analizados, cantidad de
  vulnerabilidades y qué se hizo en el registro.
- Artefacto `reescaneo-<commit>`: los tres reportes JSON de OSV-Scanner y el
  log del registro.
- Los issues creados o actualizados, con enlace a la ejecución.

### Reproducirlo en local

```bash
# Dependencias de un commit (aquí, el actual)
mkdir -p reportes/reescaneo
ESCANEO_DIR=. REPORTES_DIR=./reportes/reescaneo \
  docker compose -f docker-compose.seguridad.yml run --rm osv-reescaneo

# Imagen desplegada (digest de la ejecución o de docs/despliegue.md)
docker pull docker.io/<usuario>/eco-inversion-backend@sha256:<digest>
docker save -o reportes/reescaneo/imagen.tar docker.io/<usuario>/eco-inversion-backend@sha256:<digest>
REPORTES_DIR=./reportes/reescaneo \
  docker compose -f docker-compose.seguridad.yml run --rm osv-imagen

# Registro en simulación (no escribe en GitHub)
python .github/scripts/hallazgos_reescaneo.py --simular \
  --reporte dependencias=reportes/reescaneo/osv-dependencias.json \
  --reporte imagen-backend=reportes/reescaneo/osv-imagen.json \
  --version-desplegada <commit> --ejecucion local
```

## Limitaciones

- La imagen se identifica por el commit que informa la aplicación y la
  etiqueta `sha-<commit>`. El workflow no consulta a Render el digest exacto
  (misma limitación que en `docs/despliegue.md`).
- Si backend y frontend corren commits distintos, las dependencias se
  analizan en el commit del backend. Las dos imágenes sí se analizan cada una
  con su propio digest.
- La severidad inicial es el CVSS que publica OSV. Ajustarla según el uso real
  del paquete es parte de la investigación del hallazgo.
- La primera corrida sobre una imagen puede crear varios issues a la vez.
  Revisarlos y cerrar como `falso-positivo` o `riesgo-aceptado` (con
  justificación) los que no apliquen.
- El repositorio de Docker Hub tiene que ser público, porque el reescaneo
  descarga sin credenciales. El token de publicación vive en el environment
  `development` y no se comparte con este workflow.
