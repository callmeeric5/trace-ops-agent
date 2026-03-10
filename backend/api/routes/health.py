"""Health check routes."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "sentinel-ops-ai"}


@router.get("/ready")
async def readiness_check():
    return {"status": "ready"}
