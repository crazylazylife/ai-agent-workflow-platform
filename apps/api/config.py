"""App configuration, loaded from environment / .env via pydantic-settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://awp:awp@localhost:5432/awp"
    redis_url: str = "redis://localhost:6379/0"
    otel_service_name: str = "awp-api"


settings = Settings()
