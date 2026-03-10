"""Sentinel-Ops AI — FastAPI Application Entry Point."""

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
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("🚀 Sentinel-Ops AI starting up…")
    logger.info("🌎 Environment: %s", settings.environment)
    if settings.environment.lower() == "production" and settings.debug:
        logger.warning("DEBUG is enabled in production. Disable DEBUG for safety.")
    if (
        settings.environment.lower() == "production"
        and "*" in settings.cors_allow_origins
    ):
        logger.warning("CORS allows all origins in production. Tighten CORS settings.")
    if not settings.google_api_key:
        logger.warning("GOOGLE_API_KEY not set — diagnosis runs will fail without it.")
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

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)


app.include_router(health_router, prefix="/api")
app.include_router(logs_router, prefix="/api")
app.include_router(diagnosis_router, prefix="/api")


app.mount(
    "/",
    StaticFiles(directory=settings.frontend_dir, html=True),
    name="frontend",
)
