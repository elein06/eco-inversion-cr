# Imagen del frontend (base para 5.5 y 6.1; la revisa la política U1 del 3.4).
#
# Etapa 1: Node compila la aplicación con las dependencias del lockfile.
# Etapa 2: nginx sin privilegios sirve los archivos estáticos. Es la única que
# se publica: no lleva Node, ni el código fuente, ni node_modules.
#
# VITE_API_BASE_URL se fija al compilar porque Vite la incrusta en el bundle.
# No es un secreto: es la URL pública de la API del ambiente de destino.
# Imágenes base fijadas por digest: Renovate (7.6) propone los cambios por PR.
FROM node:26-alpine@sha256:8996bb5821d62a8fd9bb27c1cb07462f3fdce6e47d640c6a881ead0b064ce216 AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
# Commit del que sale la imagen; el despliegue lo lee en /version.txt.
ARG APP_VERSION=local
RUN npm run build && echo "${APP_VERSION}" > dist/version.txt

FROM nginxinc/nginx-unprivileged:1.30-alpine@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
# La imagen base ya usa el UID 101 (nginx); la política exige declararlo.
USER 101
EXPOSE 8080
