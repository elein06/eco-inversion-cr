# Imagen del frontend (base para 5.5 y 6.1; la revisa la política U1 del 3.4).
#
# Etapa 1: Node compila la aplicación con las dependencias del lockfile.
# Etapa 2: nginx sin privilegios sirve los archivos estáticos. Es la única que
# se publica: no lleva Node, ni el código fuente, ni node_modules.
#
# VITE_API_BASE_URL se fija al compilar porque Vite la incrusta en el bundle.
# No es un secreto: es la URL pública de la API del ambiente de destino.
FROM node:26-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.30-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
# La imagen base ya usa el UID 101 (nginx); la política exige declararlo.
USER 101
EXPOSE 8080
