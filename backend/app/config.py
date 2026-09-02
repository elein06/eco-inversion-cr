from pydantic_settings import BaseSettings, SettingsConfigDict


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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
