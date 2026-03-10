"""
User Service — Mock Microservice
==================================
Intentional Bugs:
  1. Database connection pool exhaustion — connections are acquired but
     never released on certain code paths (15% chance).
  2. Unhandled exception on specific user IDs (user_id=13 triggers a crash).
  3. Slow query simulation — random queries take 2-5 seconds.
"""

import asyncio
import random
import uuid
import json
import logging
import traceback
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("user-service")

BACKEND_LOG_URL = "http://backend:8000"
http_client: httpx.AsyncClient | None = None

# ── Simulated Connection Pool ─────────────────────────────────────────────
MAX_POOL_SIZE = 10


class FakeConnectionPool:
    """Simulates a DB connection pool with intentional leak."""

    def __init__(self, max_size: int = MAX_POOL_SIZE):
        self.max_size = max_size
        self._available = max_size
        self._leaked = 0

    @property
    def active(self):
        return self.max_size - self._available

    def acquire(self):
        if self._available <= 0:
            raise RuntimeError(
                f"Connection pool exhausted! max={self.max_size}, "
                f"leaked={self._leaked}, available=0"
            )
        self._available -= 1
        return self._available

    def release(self):
        if self._available < self.max_size:
            self._available += 1

    def leak(self):
        """BUG #1: Deliberately do NOT release the connection."""
        self._leaked += 1


pool = FakeConnectionPool()

# ── Fake user data ────────────────────────────────────────────────────────────
USERS = {
    i: {
        "id": i,
        "name": f"User_{i}",
        "email": f"user_{i}@example.com",
        "plan": random.choice(["free", "pro", "enterprise"]),
    }
    for i in range(1, 51)
}


def _structured_log(level: str, message: str, extra: dict | None = None):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "user-service",
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=5.0)
    yield
    await http_client.aclose()


app = FastAPI(title="User Service (Buggy)", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "user-service",
        "pool_available": pool._available,
        "pool_leaked": pool._leaked,
    }


@app.get("/users/{user_id}")
async def get_user(user_id: int):
    # BUG #2: Crash on unlucky number
    if user_id == 13:
        _structured_log("ERROR", "Unhandled NoneType in user lookup", {
            "user_id": user_id,
            "stack_trace": "Traceback (most recent call last):\n"
                           '  File "main.py", line 88, in get_user\n'
                           "    plan_details = user['plan_details']['tier']\n"
                           "TypeError: 'NoneType' object is not subscriptable",
        })
        raise HTTPException(status_code=500, detail="Internal server error")

    # Acquire connection
    try:
        pool.acquire()
    except RuntimeError as exc:
        _structured_log("CRITICAL", str(exc), {
            "pool_available": pool._available,
            "pool_leaked": pool._leaked,
        })
        return JSONResponse(status_code=503, content={"error": "Service Unavailable — pool exhausted"})

    # BUG #3: Slow query (20% chance)
    if random.random() < 0.20:
        delay = random.uniform(2.0, 5.0)
        _structured_log("WARN", "Slow query detected", {"delay_seconds": round(delay, 2)})
        await asyncio.sleep(delay)

    user = USERS.get(user_id)
    if not user:
        pool.release()
        return JSONResponse(status_code=404, content={"error": "User not found"})

    # BUG #1: 15% chance connection is leaked (never released)
    if random.random() < 0.15:
        pool.leak()
        _structured_log("DEBUG", "Connection not released (potential leak)", {
            "user_id": user_id,
            "pool_available": pool._available,
            "pool_leaked": pool._leaked,
        })
    else:
        pool.release()

    _structured_log("INFO", "User fetched successfully", {"user_id": user_id})
    return user
