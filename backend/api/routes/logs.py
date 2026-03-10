"""Log ingestion and query routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.models.log_entry import (
    LogBatchCreate,
    LogEntryCreate,
    LogEntryResponse,
    LogLevel,
)
from backend.services.log_store import LogStore

router = APIRouter(prefix="/logs", tags=["logs"])


@router.post("/", response_model=LogEntryResponse, status_code=201)
async def ingest_log(entry: LogEntryCreate, db: AsyncSession = Depends(get_db)):
    """Ingest a single log entry."""
    store = LogStore(db)
    orm = await store.insert(entry)
    return orm


@router.post("/batch", status_code=201)
async def ingest_batch(batch: LogBatchCreate, db: AsyncSession = Depends(get_db)):
    """Ingest multiple log entries at once."""
    store = LogStore(db)
    ids = await store.insert_batch(batch.entries)
    return {"inserted": len(ids), "ids": ids}


@router.get("/", response_model=list[LogEntryResponse])
async def query_logs(
    service: str | None = None,
    level: LogLevel | None = None,
    keyword: str | None = None,
    since_minutes: int = Query(default=60, ge=1, le=10080),
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Query log entries with optional filters."""
    store = LogStore(db)
    logs = await store.query_logs(
        service=service,
        level=level,
        since_minutes=since_minutes,
        keyword=keyword,
        limit=limit,
    )
    return logs


@router.get("/{log_id}", response_model=LogEntryResponse)
async def get_log(log_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch a single log entry by ID."""
    store = LogStore(db)
    log = await store.get_by_id(log_id)
    if not log:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Log not found")
    return log


@router.get("/errors/summary")
async def error_summary(
    since_minutes: int = Query(default=60, ge=1, le=10080),
    db: AsyncSession = Depends(get_db),
):
    """Get error/critical counts grouped by service."""
    store = LogStore(db)
    return await store.get_error_counts_by_service(since_minutes)
