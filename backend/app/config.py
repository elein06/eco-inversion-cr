from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# El .env vive en la raíz del repositorio y lo comparten backend y ETL, pero
# uvicorn se levanta desde backend/. Con una ruta relativa, pydantic-settings
# buscaría backend/.env, no lo encontraría y se iría a los valores por defecto
# de abajo —apuntando a una base equivocada sin avisar—. Por eso la ruta se
# calcula desde este archivo: backend/app/config.py -> ../../.env
RAIZ_REPO = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str = "postgresql://eco_inversion:changeme@localhost:5432/eco_inversion_cr"
    cors_origins: str = "http://localhost:5173"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # Pesos del Índice de Viabilidad. Decisión propia del equipo, no un
    # estándar oficial — se documentan aquí y se devuelven en cada respuesta
    # de /indice-viabilidad (campo pesos_usados) en vez de quedar implícitos.
    peso_ambiental: float = 0.25
    peso_inversion: float = 0.25
    peso_conectividad: float = 0.25
    peso_seguridad: float = 0.25

    # Dentro de docker-compose no hay .env montado y las variables llegan por
    # `environment:`; pydantic-settings las lee igual y el archivo ausente no
    # es un error. Un backend/.env, si existe, gana sobre el de la raíz.
    model_config = SettingsConfigDict(
        env_file=(RAIZ_REPO / ".env", RAIZ_REPO / "backend" / ".env"),
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
