"""
Log ingestion & query routes.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.log_entry import LogEntry, LogStats
from app.ingestion.parser import parse_log_entry, build_log_text
from app.storage.database import get_log_database
from app.storage.chroma_store import get_chroma_store

logger = logging.getLogger("sentinel.logs")
router = APIRouter(prefix="/api/v1/logs", tags=["Logs"])


@router.post("/ingest", status_code=201)
async def ingest_log(payload: dict):
    """
    Receive a log entry from any service.
    Accepts both structured JSON and raw text.
    Stores in both SQLite (queryable) and ChromaDB (semantic search).
    """
    try:
        entry = parse_log_entry(payload)
        db = get_log_database()
        db.add(entry)

        # Also store in ChromaDB for vector search
        try:
            text = build_log_text(entry)
            store = get_chroma_store()
            store.add_log(
                log_id=entry["log_id"],
                text=text,
                metadata={
                    "service": entry.get("service", "unknown"),
                    "level": entry.get("level", "INFO"),
                    "timestamp": entry.get("timestamp", ""),
                },
            )
        except Exception as chroma_err:
            logger.warning(f"ChromaDB insert failed (non-critical): {chroma_err}")

        return {"status": "ingested", "log_id": entry["log_id"]}
    except Exception as exc:
        logger.error(f"Failed to ingest log: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/ingest/batch", status_code=201)
async def ingest_logs_batch(payloads: list[dict]):
    """Batch ingest multiple log entries."""
    db = get_log_database()
    store = get_chroma_store()
    ingested = []

    for payload in payloads:
        try:
            entry = parse_log_entry(payload)
            db.add(entry)
            text = build_log_text(entry)
            store.add_log(
                log_id=entry["log_id"],
                text=text,
                metadata={
                    "service": entry.get("service", "unknown"),
                    "level": entry.get("level", "INFO"),
                    "timestamp": entry.get("timestamp", ""),
                },
            )
            ingested.append(entry["log_id"])
        except Exception as exc:
            logger.warning(f"Skipped log entry: {exc}")

    return {"status": "batch_ingested", "count": len(ingested), "log_ids": ingested}


@router.get("/")
async def query_logs(
    service: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
):
    """Query stored logs with optional filters."""
    db = get_log_database()
    results = db.query(service=service, level=level, limit=limit, search=search)
    return {"logs": results, "count": len(results)}


@router.get("/stats")
async def log_stats():
    """Aggregate statistics about ingested logs."""
    db = get_log_database()
    return db.stats()


@router.get("/{log_id}")
async def get_log(log_id: str):
    """Retrieve a specific log entry by ID."""
    db = get_log_database()
    entry = db.get_by_id(log_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Log not found")
    return entry


@router.get("/search/similar")
async def search_similar_logs(
    query: str = Query(..., description="Natural language query"),
    n: int = Query(10, le=50),
    service: Optional[str] = Query(None),
):
    """Semantic search across log entries using ChromaDB."""
    store = get_chroma_store()
    where = {"service": service} if service else None
    results = store.search_similar(query, n_results=n, where=where)
    return {"results": results, "count": len(results)}
