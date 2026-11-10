# Caso permitido (ítem 3.4): la etapa final declara un usuario no root.
FROM python:3.12-slim AS build
RUN pip install --no-cache-dir --prefix=/instalado uvicorn

FROM python:3.12-slim
COPY --from=build /instalado /usr/local
RUN useradd --system --no-create-home app
USER app
CMD ["python", "-m", "http.server", "8000"]
