"""Sentinel-Ops AI — Application Configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Centralised, validated application settings loaded from env / .env file."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Gemini ---
    google_api_key: str = "sk-placeholder"
    gemini_model: str = "gemini-2.5-fast"

    # --- Database ---
    database_url: str = f"sqlite+aiosqlite:///{PROJECT_ROOT / 'sentinel_ops.db'}"

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # --- Agent ---
    max_agent_iterations: int = 15
    noise_reduction_threshold: float = 0.75


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()
