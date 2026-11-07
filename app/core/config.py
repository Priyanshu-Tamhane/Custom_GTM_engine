"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Core application settings with environment variable overrides."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Environment
    ENVIRONMENT: Literal["development", "production", "testing"] = "development"
    LOG_LEVEL: str = "INFO"
    API_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "GTM Intelligence Engine"
    VERSION: str = "0.1.0"

    # PostgreSQL
    POSTGRES_USER: str = "gtm_user"
    POSTGRES_PASSWORD: str = "gtm_password"
    POSTGRES_DB: str = "gtm_intelligence"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = "postgresql+asyncpg://gtm_user:gtm_password@localhost:5432/gtm_intelligence"
    SYNC_DATABASE_URL: str = (
        "postgresql+psycopg://gtm_user:gtm_password@localhost:5432/gtm_intelligence"
    )

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM Provider settings
    LLM_PROVIDER: str = "mock"  # "mock" or "groq"
    LLM_API_KEY: SecretStr | None = None
    LLM_MODEL: str = "mock-model"
    GROQ_API_KEY: SecretStr | None = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Worker & Reliability Defaults
    DEFAULT_TIMEOUT_SECONDS: int = 15
    MAX_RETRIES: int = 3
    RATE_LIMIT_PER_MINUTE: int = 60

    @property
    def is_testing(self) -> bool:
        return self.ENVIRONMENT == "testing"


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
