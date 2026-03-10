"""Sentinel-Ops AI — Application Configuration."""

from functools import lru_cache
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Centralised, validated application settings loaded from env / .env file."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    #  Runtime
    environment: str = "development"
    log_level: str = "INFO"

    #  Gemini
    google_api_key: str = ""
    gemini_model: str = "gemini-2.5-fast"

    #  Database
    database_url: str = f"sqlite+aiosqlite:///{PROJECT_ROOT / 'sentinel_ops.db'}"

    #  Server
    debug: bool = False

    #  CORS
    cors_allow_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    cors_allow_methods: list[str] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    cors_allow_headers: list[str] = ["*"]
    cors_allow_credentials: bool = True

    # --- Frontend ---
    frontend_dir: str = "frontend"

    # --- Agent ---
    max_agent_iterations: int = 15
    noise_reduction_threshold: float = 0.75

    @field_validator(
        "cors_allow_origins",
        "cors_allow_methods",
        "cors_allow_headers",
        mode="before",
    )
    @classmethod
    def _split_csv(cls, value):
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",")]
            return [item for item in items if item]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()
