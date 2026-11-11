# Publicación y despliegue (ítems 5.5 y 6.1)

[.github/workflows/publicacion.yml](../.github/workflows/publicacion.yml)
publica en Docker Hub las imágenes que aprobaron las comprobaciones y las
despliega en Render sin reconstruirlas.

## Flujo

Se inicia al fusionar un PR en `development`:

| Job | Qué hace | Si falla |
|---|---|---|
| Comprobaciones de CI | Reutiliza `ci.yml` sobre el commit fusionado: backend (ruff, compilación, pytest), frontend (ESLint, compilación) y Seguridad (Semgrep, Gitleaks, OSV-Scanner) | No se publica ni se despliega |
| Políticas de contenedores | Reutiliza `politicas.yml` (ítem 3.4) | No se publica ni se despliega |
| Publicar en Docker Hub | Construye cada imagen **una vez**, comprueba esa imagen y publica exactamente la misma | No se despliega |
| Desplegar en Render | Despliega cada servicio **por digest** y espera a que informe el commit | El despliegue no se marca como satisfactorio |

Los jobs dependen entre sí con `needs`: uno fallido, cancelado u omitido
detiene todo lo que sigue. Ningún paso usa `continue-on-error`.

## Identidad de las imágenes (5.5)

| Imagen | Repositorio en Docker Hub |
|---|---|
| API (FastAPI) | `<usuario>/eco-inversion-backend` |
| Frontend (React + nginx sin root) | `<usuario>/eco-inversion-frontend` |

- Etiqueta `sha-<commit completo>`: identifica el commit del que salió la imagen.
- Etiqueta `development`: el último candidato aprobado de esa rama. Es solo
  una referencia; el despliegue nunca la usa.
- Digest (`sha256:...`): lo devuelve Docker Hub al publicar. Queda en el
  resumen de la ejecución y en el artefacto `version-<commit>`
  (`version.md` y `version.json`). El despliegue usa este valor.
- Cada imagen lleva el commit en `APP_VERSION`: el backend lo informa en
  `GET /health` y el frontend en `/version.txt`.

Antes de publicar, el job comprueba la imagen ya construida: que su usuario
no sea root, que la API arranque contra un PostGIS temporal y responda
`/health/listo`, que el frontend responda `/salud`, y que las dos informen el
commit esperado. Después se publica esa misma imagen con `docker push`, sin
reconstruirla. Si una imagen se reconstruye o modifica, debe pasar de nuevo
por todo el workflow.

El token de Docker Hub (`DOCKERHUB_TOKEN`) es un secreto del repositorio con
permisos de lectura y escritura solo sobre Docker Hub. Se usa con
`--password-stdin` y se cierra la sesión al terminar el paso.

## Despliegue (6.1)

Solo corre para `development` y solo si `publicar` terminó bien. Usa los deploy
hooks de Render con el parámetro `imgURL`, que indica la imagen por digest
(`docker.io/<usuario>/eco-inversion-backend@sha256:...`). Render descarga esa
imagen exacta; no compila nada.

Después espera hasta 15 minutos a que `URL_BACKEND/health` y
`URL_FRONTEND/version.txt` informen el commit desplegado, y comprueba
`/health/listo`. Si no llega a esa versión, el job falla y el despliegue no se
marca como satisfactorio.

Los deploy hooks son secretos del environment `development` de GitHub: solo
los ven los jobs que declaran ese environment. Cada hook solo permite
desplegar su servicio, a diferencia de una API key de Render, que da acceso a
toda la cuenta.

## Ambiente: Render

| Componente | Tipo en Render | Imagen o versión | Configuración |
|---|---|---|---|
| `eco-inversion-api-elein` | Web Service, imagen existente | `docker.io/<usuario>/eco-inversion-backend` | Puerto 8000, health check `/health/listo` |
| `eco-inversion-cr-elein` | Web Service, imagen existente | `docker.io/<usuario>/eco-inversion-frontend` | Puerto 8080, health check `/salud` |
| `eco-inversion-db` | PostgreSQL 16 con PostGIS | Administrada por Render | La API usa la URL interna. El acceso externo se limita en Access Control a la IP de quien carga el esquema y se quita después |

Plan gratuito y región Oregon. Render termina HTTPS en sus dominios
`*.onrender.com`.

### Configuración y secretos

No hay valores secretos en Git, en las imágenes ni en los logs.

| Nombre | Dónde se guarda | Lo usa | Quién puede verlo o cambiarlo |
|---|---|---|---|
| `DOCKERHUB_TOKEN` | Secreto del repositorio en GitHub | Job Publicar | Administradores del repositorio |
| `RENDER_DEPLOY_HOOK_BACKEND`, `RENDER_DEPLOY_HOOK_FRONTEND` | Secretos del environment `development` | Job Desplegar | Administradores del repositorio |
| `DOCKERHUB_USUARIO`, `URL_BACKEND`, `URL_FRONTEND` | Variables de Actions (no son secretos) | Publicar y Desplegar | Colaboradores del repositorio |
| `DATABASE_URL` | Variable de entorno del servicio API en Render | API | Miembros del workspace de Render |
| `JWT_SECRET` | Variable de entorno del servicio API en Render | API | Miembros del workspace de Render |
| `CORS_ORIGINS` | Variable de entorno del servicio API en Render (URL del frontend) | API | Miembros del workspace de Render |

Para reemplazar uno: generar el valor nuevo, actualizarlo en GitHub o en
Render y volver a desplegar. Un deploy hook expuesto se regenera en Render
(Settings → Deploy Hook → Regenerate). El token de Docker Hub se revoca en
Account settings → Personal access tokens.

`VITE_API_BASE_URL` sale de `URL_BACKEND` y se incrusta en el frontend al
compilar. No es un secreto: es la URL pública de la API.

### Reproducir el ambiente (una vez)

1. Docker Hub: crear un token de lectura y escritura y guardarlo en GitHub
   como `DOCKERHUB_TOKEN`. Guardar el usuario como variable `DOCKERHUB_USUARIO`.
2. Render: crear el Postgres `eco-inversion-db` y cargar el esquema con su
   URL externa (no queda guardada en ningún archivo):
   ```bash
   docker run --rm -v "${PWD}/db:/db:ro" postgis/postgis:16-3.4 \
     psql "<URL externa>" -f /db/schema.sql -f /db/02_usuarios_escenarios.sql
   ```
3. GitHub: variables `URL_BACKEND` y `URL_FRONTEND`, y el environment
   `development`.
4. Fusionar en `development`. La primera ejecución publica las imágenes; el
   job Desplegar falla porque todavía no hay hooks.
5. Render: crear los dos Web Services desde **Existing Image** con la etiqueta
   `:development`, con los nombres de la tabla, y cargar las variables de la
   API. Copiar el Deploy Hook de cada uno a los secretos del environment.
6. En la ejecución del paso 4: **Re-run failed jobs**. Desplegar usa los
   digests ya publicados, sin reconstruir.

## Demostración: un check fallido impide publicar

Las ramas `demo/**` ejecutan el mismo workflow, pero nunca etiquetan
`development` ni despliegan. Con un defecto controlado:

```bash
git checkout -b demo/publicacion-bloqueada origin/development
# en backend/Dockerfile cambiar "USER app" por "USER root"
git commit -am "Demo 5.5: defecto controlado (USER root)"
git push -u origin demo/publicacion-bloqueada
```

Resultado esperado: Políticas falla con `[U1]` y Publicar y Desplegar quedan
omitidos, sin imagen nueva en Docker Hub. Después se borra la rama.

## Limitaciones

- La URL de la API queda dentro de la imagen del frontend, así que esa imagen
  solo sirve para este ambiente. Otro ambiente necesita otra imagen, que debe
  volver a pasar el workflow.
- El esquema de la base se carga a mano una vez. No hay migraciones
  automáticas, y una versión que cambie el esquema no se puede revertir
  solo con la imagen anterior.
- El ETL no se ejecuta en Render: el mapa usa los datos que tenga la base o
  los datos de respaldo del frontend.
- Plan gratuito: los servicios se apagan sin tráfico y tardan en arrancar, y
  el Postgres gratuito vence a los 30 días.
- El job no ejecuta el DAST (4.7) ni E2E contra la versión desplegada; eso
  corresponde a 6.5.
- La comprobación de identidad usa el commit que informa la aplicación. Que
  Render corre exactamente ese digest se ve en su panel (Events), no lo
  consulta el workflow.
