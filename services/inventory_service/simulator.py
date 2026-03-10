"""Simulated Inventory Service with intentional bugs.

Bugs included:
1. Redis cache penetration — cache miss storm causing database overload.
2. Race condition — concurrent stock updates causing negative inventory.
"""

from __future__ import annotations

import asyncio
import random
from uuid import uuid4

import httpx

LOG_ENDPOINT = "http://localhost:8000/api/logs/"
SERVICE_NAME = "inventory-service"


async def send_log(
    level: str,
    message: str,
    stack_trace: str | None = None,
    trace_id: str | None = None,
    metadata_json: str | None = None,
):
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
        pass


async def simulate_normal_operation():
    messages = [
        "Stock check for SKU-{sku}: {qty} units available",
        "Reserved {qty} units of SKU-{sku} for order #ORD-{order}",
        "Cache hit for SKU-{sku} (TTL remaining: {ttl}s)",
        "Inventory sync completed: {count} SKUs updated from warehouse feed",
    ]
    sku = random.randint(1000, 9999)
    for msg in messages:
        await send_log(
            "INFO",
            msg.format(
                sku=sku,
                qty=random.randint(1, 500),
                order=random.randint(10000, 99999),
                ttl=random.randint(10, 300),
                count=random.randint(50, 500),
            ),
        )
        await asyncio.sleep(random.uniform(0.1, 0.4))


async def simulate_cache_penetration():
    """BUG: Redis cache miss storm."""
    trace_id = str(uuid4())
    await send_log(
        "WARNING",
        "Redis cache miss rate spiked to 94% in last 60s. "
        "Hot key pattern detected: SKU-0000 through SKU-0050 all expired simultaneously "
        "(batch TTL expiry). 2,847 requests fell through to database.",
        trace_id=trace_id,
        metadata_json='{"cache_miss_rate": 0.94, "hot_keys": 50, "db_queries": 2847}',
    )
    await asyncio.sleep(0.5)
    await send_log(
        "ERROR",
        "Database connection timeout — inventory_db is overloaded due to cache penetration. "
        "Query queue depth: 1,203. Average query time: 8.7s (normal: 15ms). "
        "Root cause: all hot SKU cache entries share the same TTL base time, "
        "causing synchronized expiry.",
        trace_id=trace_id,
        stack_trace=(
            "Traceback (most recent call last):\n"
            '  File "inventory_service/cache.py", line 89, in get_stock\n'
            "    cached = await redis.get(f'stock:{sku}')\n"
            "    # cache miss — fallback to DB\n"
            '  File "inventory_service/repository.py", line 45, in get_stock_from_db\n'
            "    result = await db.execute(query, timeout=5)\n"
            "asyncio.TimeoutError: Database query timed out after 5s\n"
            "\n"
            "CachePenetrationError: 94% cache miss rate detected"
        ),
        metadata_json='{"queue_depth": 1203, "avg_query_time_ms": 8700, "normal_query_time_ms": 15}',
    )
    await send_log(
        "CRITICAL",
        "Inventory service returning stale data — fallback to last-known-good cache "
        "activated. Orders may be accepted for out-of-stock items. "
        "Affected SKU range: SKU-0000 to SKU-0050.",
        trace_id=trace_id,
        metadata_json='{"fallback_mode": true, "stale_data_age_seconds": 340}',
    )


async def simulate_race_condition():
    """BUG: Concurrent stock updates causing negative inventory."""
    trace_id = str(uuid4())
    sku = f"SKU-{random.randint(1000, 9999)}"
    await send_log(
        "ERROR",
        f"Negative inventory detected for {sku}: current_stock=-3. "
        "Two concurrent reservation requests (ORD-44821, ORD-44822) both read stock=2 "
        "and decremented without locking. Race condition in StockReservation.reserve().",
        trace_id=trace_id,
        stack_trace=(
            "Traceback (most recent call last):\n"
            '  File "inventory_service/reservation.py", line 112, in reserve\n'
            "    current = await self.get_stock(sku)  # read: 2\n"
            "    # ... other thread also reads 2 here ...\n"
            "    new_stock = current - quantity  # 2 - 5 = -3\n"
            "    await self.update_stock(sku, new_stock)\n"
            "IntegrityError: CHECK constraint failed: stock >= 0\n"
            "\n"
            "Fix: Use SELECT ... FOR UPDATE or optimistic locking"
        ),
        metadata_json=f'{{"sku": "{sku}", "current_stock": -3, "concurrent_orders": ["ORD-44821", "ORD-44822"]}}',
    )


async def run_simulator():
    print(f"📦 {SERVICE_NAME} simulator started")
    scenarios = [
        (simulate_normal_operation, 0.5),
        (simulate_cache_penetration, 0.25),
        (simulate_race_condition, 0.25),
    ]
    while True:
        funcs, weights = zip(*scenarios)
        chosen = random.choices(funcs, weights=weights, k=1)[0]
        await chosen()
        await asyncio.sleep(random.uniform(3, 10))


if __name__ == "__main__":
    asyncio.run(run_simulator())
