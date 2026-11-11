# Caso rechazado (ítem 3.4): la etapa final vuelve a root.
FROM python:3.12-slim
RUN useradd --system --no-create-home app
USER app
RUN echo "instalación que requiere root"
USER root
CMD ["python", "-m", "http.server", "8000"]
