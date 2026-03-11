"""Seed the database with realistic log data for demo / development.

Run with: python -m scripts.seed_logs
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from backend.db.database import init_db, async_session_factory
from backend.models.log_entry import LogEntryORM, LogLevel


def _make_logs() -> list[LogEntryORM]:
    """Generate a batch of realistic log entries covering ~60 minutes."""
    now = datetime.now(timezone.utc)
    logs: list[LogEntryORM] = []

    services_info = {
        "order-service": [
            ("Processing order #ORD-{id}", LogLevel.INFO),
            ("Order #ORD-{id} committed to database", LogLevel.INFO),
            ("Payment validated for order #ORD-{id}", LogLevel.INFO),
        ],
        "inventory-service": [
            ("Stock check for SKU-{id}: {qty} units available", LogLevel.INFO),
            ("Cache hit for SKU-{id}", LogLevel.INFO),
            ("Inventory sync completed: {qty} SKUs updated", LogLevel.INFO),
        ],
        "payment-service": [
            ("Payment initiated for order #ORD-{id}: ${amt:.2f}", LogLevel.INFO),
            ("Gateway response: APPROVED (txn_id=TXN-{id})", LogLevel.INFO),
        ],
    }

    for _ in range(500):
        service = random.choice(list(services_info.keys()))
        template, level = random.choice(services_info[service])
        ts = now - timedelta(
            minutes=random.randint(1, 59), seconds=random.randint(0, 59)
        )
        msg = template.format(
            id=random.randint(10000, 99999),
            qty=random.randint(1, 500),
            amt=random.uniform(10, 500),
        )
        logs.append(
            LogEntryORM(
                id=str(uuid4()),
                timestamp=ts,
                service=service,
                level=level,
                message=msg,
                trace_id=str(uuid4()),
            )
        )

    trace_id = str(uuid4())
    base_time = now - timedelta(minutes=15)
    logs.extend(
        [
            LogEntryORM(
                id=str(uuid4()),
                timestamp=base_time,
                service="order-service",
                level=LogLevel.WARNING,
                message="Connection pool utilization at 85% (170/200 connections in use)",
                trace_id=trace_id,
                metadata_json='{"pool_size": 200, "active": 170}',
            ),
            LogEntryORM(
                id=str(uuid4()),
                timestamp=base_time + timedelta(seconds=30),
                service="order-service",
                level=LogLevel.ERROR,
                message="Connection pool exhausted — cannot acquire new connection after 30s timeout. Active: 200/200, Waiting: 47",
                trace_id=trace_id,
                stack_trace=(
                    "Traceback (most recent call last):\n"
                    '  File "order_service/repository.py", line 142, in find_by_status\n'
                    "    conn = await self.pool.acquire(timeout=30)\n"
                    "asyncio.TimeoutError: Connection pool exhausted"
                ),
                metadata_json='{"pool_size": 200, "active": 200, "waiting_threads": 47}',
            ),
            LogEntryORM(
                id=str(uuid4()),
                timestamp=base_time + timedelta(seconds=60),
                service="order-service",
                level=LogLevel.CRITICAL,
                message="Service degradation — order endpoint returning 503. DB connection pool leak in OrderRepository.findByStatus()",
                trace_id=trace_id,
                metadata_json='{"http_status": 503, "error_rate": "73%"}',
            ),
        ]
    )

    trace_id2 = str(uuid4())
    base_time2 = now - timedelta(minutes=10)
    logs.extend(
        [
            LogEntryORM(
                id=str(uuid4()),
                timestamp=base_time2,
                service="inventory-service",
                level=LogLevel.WARNING,
                message="Redis cache miss rate spiked to 94%. Hot key batch TTL expiry. 2847 requests fell through to DB.",
                trace_id=trace_id2,
                metadata_json='{"cache_miss_rate": 0.94, "db_queries": 2847}',
            ),
            LogEntryORM(
                id=str(uuid4()),
                timestamp=base_time2 + timedelta(seconds=20),
                service="inventory-service",
                level=LogLevel.ERROR,
                message="Database connection timeout due to cache penetration. Query queue: 1203, Avg query time: 8.7s",
                trace_id=trace_id2,
                stack_trace=(
                    "Traceback (most recent call last):\n"
                    '  File "inventory_service/repository.py", line 45, in get_stock_from_db\n'
                    "    result = await db.execute(query, timeout=5)\n"
                    "asyncio.TimeoutError: Database query timed out"
                ),
                metadata_json='{"queue_depth": 1203, "avg_query_time_ms": 8700}',
            ),
            LogEntryORM(
                id=str(uuid4()),
                timestamp=base_time2 + timedelta(seconds=40),
                service="inventory-service",
                level=LogLevel.CRITICAL,
                message="Inventory service returning stale data. Fallback cache activated. Orders may accept out-of-stock items.",
                trace_id=trace_id2,
            ),
        ]
    )

    trace_id3 = str(uuid4())
    base_time3 = now - timedelta(minutes=5)
    logs.extend(
        [
            LogEntryORM(
                id=str(uuid4()),
                timestamp=base_time3,
                service="payment-service",
                level=LogLevel.WARNING,
                message="Stripe gateway response time elevated: 4.8s (SLA: 2s)",
                trace_id=trace_id3,
                metadata_json='{"gateway": "stripe", "response_time_ms": 4800}',
            ),
            LogEntryORM(
                id=str(uuid4()),
                timestamp=base_time3 + timedelta(seconds=15),
                service="payment-service",
                level=LogLevel.ERROR,
                message="Payment gateway timeout after 10s. Stripe HTTP 504. Retry without idempotency key.",
                trace_id=trace_id3,
                stack_trace=(
                    "Traceback (most recent call last):\n"
                    '  File "payment_service/gateway.py", line 56, in charge\n'
                    "    response = await self.client.post(..., timeout=10)\n"
                    "httpx.ReadTimeout: timed out after 10s"
                ),
                metadata_json='{"gateway": "stripe", "http_status": 504, "has_idempotency_key": false}',
            ),
            LogEntryORM(
                id=str(uuid4()),
                timestamp=base_time3 + timedelta(seconds=30),
                service="payment-service",
                level=LogLevel.CRITICAL,
                message="DUPLICATE CHARGE for order #ORD-55123! Two charges of $247.50. Missing idempotency key. Refund required.",
                trace_id=trace_id3,
                stack_trace=(
                    "Traceback (most recent call last):\n"
                    '  File "payment_service/retry.py", line 33, in retry_charge\n'
                    "    result = await gateway.charge(amount=247.50)\n"
                    "DuplicateChargeError: Two successful charges for same order"
                ),
                metadata_json='{"order_id": "ORD-55123", "amount": 247.50, "duplicate_count": 2, "needs_refund": true}',
            ),
        ]
    )

    return logs


async def seed():
    """Initialize the database and insert seed logs."""
    await init_db()
    logs = _make_logs()

    async with async_session_factory() as session:
        session.add_all(logs)
        await session.commit()

    print(f"✅ Seeded {len(logs)} log entries")
    print("   - ~500 normal INFO logs")
    print("   - 3 bug scenarios (connection leak, cache penetration, duplicate charge)")


if __name__ == "__main__":
    asyncio.run(seed())
