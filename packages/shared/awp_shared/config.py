"""Shared settings for the data layer + LLM provider (used by API, worker, Alembic)."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-root .env, resolved from this file so it's found no matter the process cwd.
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class SharedSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    # SYNC DSN for SQLAlchemy/Alembic/Celery (psycopg3 driver).
    database_url_sync: str = "postgresql+psycopg://awp:awp@localhost:5432/awp"

    # --- LLM (provider-agnostic; "mock" by default so the platform runs at $0) ---
    # Set LLM_PROVIDER + LLM_API_KEY (+ optional LLM_BASE_URL / LLM_MODEL / LLM_MODELS)
    # in .env to use a real model. Providers using an OpenAI-compatible API work as-is.
    llm_provider: str = "mock"          # mock | openai | groq | openrouter | ollama | ...
    llm_api_key: str = ""
    llm_base_url: str = ""              # override; otherwise derived from the provider
    llm_model: str = "mock-gpt"        # default model used when a run doesn't pick one
    llm_models: str = ""               # comma-separated list offered in the UI picker

    @property
    def llm_model_list(self) -> list[str]:
        items = [m.strip() for m in self.llm_models.split(",") if m.strip()]
        return items or [self.llm_model]


shared_settings = SharedSettings()
