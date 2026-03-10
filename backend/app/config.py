"""
Sentinel-Ops AI — Backend Configuration
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Gemini ────────────────────────────────────────────────────────────
    gemini_api_key: str = ""

    # ── ChromaDB ──────────────────────────────────────────────────────────
    chroma_persist_dir: str = "./chroma_data"

    # ── Server ────────────────────────────────────────────────────────────
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # ── Mock Service URLs ─────────────────────────────────────────────────
    api_gateway_url: str = "http://api-gateway:8001"
    user_service_url: str = "http://user-service:8002"
    cache_service_url: str = "http://cache-service:8003"

    # ── CORS ──────────────────────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
