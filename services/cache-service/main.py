"""
Cache Service — Mock Microservice
====================================
Intentional Bugs:
  1. Cache penetration — when a key doesn't exist in the "cache" (Redis sim),
     the service hammers the "database" every single time instead of caching
     the null result. Under load this causes cascading failures.
  2. No TTL management — cached items never expire, leading to stale data.
  3. Thundering herd — no locking on cache miss; concurrent requests for
     the same missing key all trigger expensive "DB" lookups simultaneously.
"""

import asyncio
import random
import uuid
import json
import logging
import time
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("cache-service")

BACKEND_LOG_URL = "http://backend:8000"
http_client: httpx.AsyncClient | None = None

# ── Simulated In-Memory Cache ────────────────────────────────────────────────
_cache: dict[str, dict] = {}

# Pre-populate some keys
for i in range(1, 21):
    _cache[f"product:{i}"] = {
        "id": i,
        "name": f"Product_{i}",
        "price": round(random.uniform(9.99, 299.99), 2),
        "cached_at": datetime.now(timezone.utc).isoformat(),  # BUG #2: never refreshed
    }

# Track concurrent "DB" lookups per key (for thundering herd detection)
_inflight: dict[str, int] = {}


def _structured_log(level: str, message: str, extra: dict | None = None):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "cache-service",
        "level": level,
        "message": message,
        "log_id": str(uuid.uuid4()),
        **(extra or {}),
    }
    logger.info(json.dumps(entry))
    try:
        if http_client:
            asyncio.create_task(
                http_client.post(f"{BACKEND_LOG_URL}/api/v1/logs/ingest", json=entry)
            )
    except Exception:
        pass
    return entry


async def _simulate_db_lookup(key: str) -> dict | None:
    """Simulate an expensive database query (500ms-2s)."""
    delay = random.uniform(0.5, 2.0)
    _structured_log("WARN", "Cache MISS — falling back to database", {
        "key": key,
        "estimated_db_latency_ms": round(delay * 1000),
    })
    await asyncio.sleep(delay)

    # 30% of unknown keys genuinely don't exist in "DB" either
    if random.random() < 0.30:
        _structured_log("WARN", "Key not found in database either", {"key": key})
        return None

    return {
        "id": key,
        "name": f"DynamicProduct_{key}",
        "price": round(random.uniform(9.99, 299.99), 2),
        "source": "database",
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=5.0)
    yield
    await http_client.aclose()


app = FastAPI(title="Cache Service (Buggy)", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "cache-service",
        "cache_size": len(_cache),
        "inflight_lookups": dict(_inflight),
    }


@app.get("/cache/{key}")
async def get_cache(key: str):
    start = time.monotonic()

    # Cache HIT
    if key in _cache:
        _structured_log("INFO", "Cache HIT", {"key": key})
        return _cache[key]

    # ── Cache MISS path (all bugs live here) ──────────────────────────────

    # BUG #3: Thundering herd — track concurrent inflight lookups
    _inflight[key] = _inflight.get(key, 0) + 1
    if _inflight[key] > 1:
        _structured_log("WARN", "Thundering herd detected", {
            "key": key,
            "concurrent_lookups": _inflight[key],
        })

    result = await _simulate_db_lookup(key)

    _inflight[key] = max(0, _inflight.get(key, 1) - 1)

    if result is None:
        # BUG #1: Cache penetration — null result is NOT cached.
        # Every subsequent request for this key will hit the DB again.
        _structured_log("ERROR", "Cache penetration — null not cached", {
            "key": key,
            "elapsed_ms": round((time.monotonic() - start) * 1000),
        })
        return JSONResponse(status_code=404, content={"error": "Key not found"})

    # Store in cache (BUG #2: no TTL — this entry will live forever)
    _cache[key] = result
    _structured_log("INFO", "Stored in cache (no TTL)", {
        "key": key,
        "elapsed_ms": round((time.monotonic() - start) * 1000),
    })
    return result


@app.get("/cache")
async def list_cache():
    """Debug endpoint: list all cached keys."""
    return {"keys": list(_cache.keys()), "total": len(_cache)}
