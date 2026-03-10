"""
API Gateway — Mock Microservice
================================
Intentional Bugs:
  1. Random latency spikes (simulates downstream timeout cascading)
  2. Intermittent 502 errors when forwarding to user-service
  3. Memory leak via accumulating request history list that never gets cleared
"""

import asyncio
import random
import time
import uuid
import logging
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

# ── Logging Setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",  # JSON logs will be self-contained
)
logger = logging.getLogger("api-gateway")

# ── BUG #3: Memory leak — this list grows indefinitely ────────────────────
_request_history: list[dict] = []

# ── HTTP client for downstream calls ──────────────────────────────────────
USER_SERVICE_URL = "http://user-service:8002"
CACHE_SERVICE_URL = "http://cache-service:8003"
BACKEND_LOG_URL = "http://backend:8000"

http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=5.0)
    yield
    await http_client.aclose()


app = FastAPI(title="API Gateway (Buggy)", lifespan=lifespan)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _structured_log(level: str, message: str, extra: dict | None = None):
    """Emit a structured JSON log line and forward it to the backend."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "api-gateway",
        "level": level,
        "message": message,
        "log_id": str(uuid.uuid4()),
        **(extra or {}),
    }
    logger.info(json.dumps(entry))
    # Fire-and-forget log shipping
    try:
        if http_client:
            asyncio.create_task(
                http_client.post(f"{BACKEND_LOG_URL}/api/v1/logs/ingest", json=entry)
            )
    except Exception:
        pass
    return entry


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "api-gateway", "request_history_size": len(_request_history)}


@app.get("/api/users/{user_id}")
async def get_user(user_id: int, request: Request):
    start = time.monotonic()

    # BUG #3: Append every request — never pruned
    _request_history.append({
        "path": str(request.url),
        "time": datetime.now(timezone.utc).isoformat(),
        "headers": dict(request.headers),
    })

    # BUG #1: Random latency spike (10% chance of 3-8s delay)
    if random.random() < 0.10:
        delay = random.uniform(3.0, 8.0)
        _structured_log("WARN", "Latency spike detected", {"delay_seconds": round(delay, 2)})
        await asyncio.sleep(delay)

    # BUG #2: Intermittent 502 (5% chance)
    if random.random() < 0.05:
        _structured_log("ERROR", "Bad gateway — upstream unreachable", {
            "upstream": USER_SERVICE_URL,
            "status_code": 502,
        })
        return JSONResponse(status_code=502, content={"error": "Bad Gateway"})

    # Forward to user-service
    try:
        resp = await http_client.get(f"{USER_SERVICE_URL}/users/{user_id}")
        elapsed = round(time.monotonic() - start, 4)
        _structured_log("INFO", "Request completed", {
            "user_id": user_id,
            "upstream_status": resp.status_code,
            "elapsed_seconds": elapsed,
        })
        return Response(content=resp.content, status_code=resp.status_code,
                        media_type="application/json")
    except httpx.TimeoutException:
        _structured_log("ERROR", "Upstream timeout", {
            "upstream": USER_SERVICE_URL,
            "timeout_seconds": 5.0,
        })
        return JSONResponse(status_code=504, content={"error": "Gateway Timeout"})
    except Exception as exc:
        _structured_log("ERROR", "Unexpected gateway error", {"error": str(exc)})
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/cache/{key}")
async def get_cache(key: str):
    """Proxy to cache-service."""
    try:
        resp = await http_client.get(f"{CACHE_SERVICE_URL}/cache/{key}")
        return Response(content=resp.content, status_code=resp.status_code,
                        media_type="application/json")
    except Exception as exc:
        _structured_log("ERROR", "Cache proxy error", {"error": str(exc)})
        return JSONResponse(status_code=500, content={"error": str(exc)})
