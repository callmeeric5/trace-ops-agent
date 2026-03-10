"""Sentinel-Ops AI — FastAPI Application Entry Point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.routes.diagnosis import router as diagnosis_router
from backend.api.routes.health import router as health_router
from backend.api.routes.logs import router as logs_router
from backend.config import get_settings
from backend.db.database import init_db

logger = logging.getLogger("sentinel-ops")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown hooks."""
    logging.basicConfig(
        level=logging.DEBUG if get_settings().debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("🚀 Sentinel-Ops AI starting up…")
    await init_db()
    logger.info("✅ Database tables created / verified")
    yield
    logger.info("👋 Sentinel-Ops AI shutting down…")


app = FastAPI(
    title="Sentinel-Ops AI",
    description=(
        "Production-grade Reasoning Agent for diagnosing system failures. "
        "Analyzes logs, metrics, and traces using a ReAct agent loop."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# --- CORS for local frontend development ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Register API routes ---
app.include_router(health_router, prefix="/api")
app.include_router(logs_router, prefix="/api")
app.include_router(diagnosis_router, prefix="/api")

# --- Serve the frontend as static files ---
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
