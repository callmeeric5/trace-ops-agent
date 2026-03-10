"""
Sentinel-Ops AI — Main FastAPI Application
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import logs, diagnosis, actions
from app.api import sse

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("sentinel")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Sentinel-Ops AI backend starting...")
    logger.info(f"   Gemini API Key: {'✅ configured' if settings.gemini_api_key else '❌ missing'}")
    logger.info(f"   ChromaDB dir: {settings.chroma_persist_dir}")
    yield
    logger.info("Sentinel-Ops AI backend shutting down...")


app = FastAPI(
    title="Sentinel-Ops AI",
    description="Production-grade fault diagnosis agent with evidence-anchored reasoning",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(logs.router)
app.include_router(diagnosis.router)
app.include_router(actions.router)
app.include_router(sse.router)


@app.get("/")
async def root():
    return {
        "name": "Sentinel-Ops AI",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    from app.storage.database import get_log_database
    db = get_log_database()
    return {
        "status": "healthy",
        "log_count": db.count(),
        "gemini_configured": bool(settings.gemini_api_key),
    }
