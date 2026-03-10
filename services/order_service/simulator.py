"""Simulated Order Service with intentional bugs.

Bugs included:
1. Database connection pool leak — connections are opened but never properly
   closed under certain error paths.
2. Intermittent NullPointerError — missing null check on optional user data.
3. Slow query — unindexed query causes periodic latency spikes.
"""

from __future__ import annotations

import asyncio
import random
import traceback
from datetime import datetime, timezone
from uuid import uuid4

import httpx

LOG_ENDPOINT = "http://localhost:8000/api/logs/"
SERVICE_NAME = "order-service"


async def send_log(
    level: str,
    message: str,
    stack_trace: str | None = None,
    trace_id: str | None = None,
    metadata_json: str | None = None,
):
    """Send a log entry to the Sentinel-Ops backend."""
    payload = {
        "service": SERVICE_NAME,
        "level": level,
        "message": message,
        "trace_id": trace_id or str(uuid4()),
        "stack_trace": stack_trace,
        "metadata_json": metadata_json,
    }
    try:
        async with httpx.AsyncClient() as client:
            await client.post(LOG_ENDPOINT, json=payload, timeout=5)
    except Exception:
        pass  # Don't crash the simulator if logging fails


async def simulate_normal_operation():
    """Emit normal INFO-level operational logs."""
    messages = [
        "Processing order #ORD-{order_id}",
        "Payment validated for order #ORD-{order_id}",
        "Inventory check passed for order #ORD-{order_id}",
        "Order #ORD-{order_id} committed to database",
        "Email confirmation queued for order #ORD-{order_id}",
    ]
    order_id = random.randint(10000, 99999)
    for msg in messages:
        await send_log("INFO", msg.format(order_id=order_id))
        await asyncio.sleep(random.uniform(0.1, 0.5))


async def simulate_db_connection_leak():
    """BUG: Database connection pool leak."""
    trace_id = str(uuid4())
    await send_log(
        "WARNING",
        "Connection pool utilization at 85% (170/200 connections in use)",
        trace_id=trace_id,
        metadata_json='{"pool_size": 200, "active": 170, "idle": 30}',
    )
    await asyncio.sleep(1)
    await send_log(
        "ERROR",
        "Connection pool exhausted — cannot acquire new connection after 30s timeout. "
        "Possible connection leak detected in OrderRepository.findByStatus(). "
        "Active connections: 200/200, Waiting threads: 47",
        trace_id=trace_id,
        stack_trace=(
            "Traceback (most recent call last):\n"
            '  File "order_service/repository.py", line 142, in find_by_status\n'
            "    conn = await self.pool.acquire(timeout=30)\n"
            '  File "asyncpg/pool.py", line 189, in acquire\n'
            "    raise asyncio.TimeoutError()\n"
            "asyncio.TimeoutError: Connection pool exhausted\n"
            "\n"
            "During handling of the above exception, another exception occurred:\n"
            '  File "order_service/handlers.py", line 78, in get_pending_orders\n'
            "    orders = await repo.find_by_status('pending')\n"
            "ConnectionPoolExhaustedError: All 200 connections are in use"
        ),
        metadata_json='{"pool_size": 200, "active": 200, "waiting_threads": 47}',
    )
    await asyncio.sleep(0.5)
    await send_log(
        "CRITICAL",
        "Service degradation — order creation endpoint returning 503. "
        "Database connection pool leak confirmed. "
        "Root cause: OrderRepository.findByStatus() opens connections in a loop "
        "without closing them when an exception occurs in the mapping phase.",
        trace_id=trace_id,
        metadata_json='{"http_status": 503, "affected_endpoint": "/api/orders", "error_rate": "73%"}',
    )


async def simulate_null_pointer():
    """BUG: Missing null check on optional user data."""
    trace_id = str(uuid4())
    await send_log(
        "ERROR",
        "NullPointerError in OrderProcessor.calculateDiscount() — "
        "user.loyalty_tier is None for guest user user_id=USR-88291",
        trace_id=trace_id,
        stack_trace=(
            "Traceback (most recent call last):\n"
            '  File "order_service/processor.py", line 67, in calculate_discount\n'
            "    discount = TIER_DISCOUNTS[user.loyalty_tier]\n"
            "TypeError: 'NoneType' object is not subscriptable\n"
            "\n"
            "Context: user_id=USR-88291 is a guest checkout (no loyalty_tier).\n"
            "The TIER_DISCOUNTS dict does not have a None key."
        ),
        metadata_json='{"user_id": "USR-88291", "is_guest": true, "loyalty_tier": null}',
    )


async def simulate_slow_query():
    """BUG: Unindexed query causes latency spikes."""
    trace_id = str(uuid4())
    await send_log(
        "WARNING",
        "Slow query detected: SELECT * FROM orders WHERE created_at > ? AND status = ? "
        "took 12.4s (threshold: 1s). Missing index on (created_at, status).",
        trace_id=trace_id,
        metadata_json='{"query_time_ms": 12400, "threshold_ms": 1000, "table": "orders"}',
    )
    await send_log(
        "ERROR",
        "Request timeout on GET /api/orders/recent — upstream took 15.2s, "
        "gateway timeout at 10s. Correlated with slow query on orders table.",
        trace_id=trace_id,
        metadata_json='{"endpoint": "/api/orders/recent", "upstream_time_ms": 15200, "gateway_timeout_ms": 10000}',
    )


async def run_simulator():
    """Run the order service simulator in a loop."""
    print(f"🛒 {SERVICE_NAME} simulator started")
    scenarios = [
        (simulate_normal_operation, 0.5),     # 50% normal
        (simulate_db_connection_leak, 0.2),    # 20% connection leak
        (simulate_null_pointer, 0.15),         # 15% null pointer
        (simulate_slow_query, 0.15),           # 15% slow query
    ]
    while True:
        funcs, weights = zip(*scenarios)
        chosen = random.choices(funcs, weights=weights, k=1)[0]
        await chosen()
        await asyncio.sleep(random.uniform(2, 8))


if __name__ == "__main__":
    asyncio.run(run_simulator())
