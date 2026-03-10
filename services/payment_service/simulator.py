"""Simulated Payment Service with intentional bugs.

Bugs included:
1. Third-party gateway timeout — payment provider intermittently unavailable.
2. Idempotency violation — duplicate charges on retry.
"""

from __future__ import annotations

import asyncio
import random
from uuid import uuid4

import httpx

LOG_ENDPOINT = "http://localhost:8000/api/logs/"
SERVICE_NAME = "payment-service"


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
        "Payment initiated for order #ORD-{order}: ${amount:.2f}",
        "Gateway response: APPROVED (txn_id=TXN-{txn})",
        "Payment record persisted for TXN-{txn}",
        "Webhook sent to order-service: payment_confirmed",
    ]
    order = random.randint(10000, 99999)
    txn = random.randint(100000, 999999)
    amount = random.uniform(10, 500)
    for msg in messages:
        await send_log(
            "INFO",
            msg.format(order=order, amount=amount, txn=txn),
        )
        await asyncio.sleep(random.uniform(0.1, 0.3))


async def simulate_gateway_timeout():
    """BUG: Third-party payment gateway timeout."""
    trace_id = str(uuid4())
    order = random.randint(10000, 99999)
    await send_log(
        "WARNING",
        f"Payment gateway response time elevated: 4.8s for order #ORD-{order} "
        "(SLA threshold: 2s). Stripe API experiencing degraded performance.",
        trace_id=trace_id,
        metadata_json=f'{{"gateway": "stripe", "response_time_ms": 4800, "threshold_ms": 2000, "order_id": "ORD-{order}"}}',
    )
    await asyncio.sleep(1)
    await send_log(
        "ERROR",
        f"Payment gateway timeout for order #ORD-{order} after 10s. "
        "Stripe returned HTTP 504. Payment status UNKNOWN — "
        "cannot determine if charge was captured. Retry logic activated but "
        "idempotency key was not included in the original request.",
        trace_id=trace_id,
        stack_trace=(
            "Traceback (most recent call last):\n"
            '  File "payment_service/gateway.py", line 56, in charge\n'
            "    response = await self.client.post(\n"
            "        'https://api.stripe.com/v1/charges',\n"
            "        data=payload,\n"
            "        timeout=10\n"
            "    )\n"
            "httpx.ReadTimeout: timed out after 10s\n"
            "\n"
            "WARNING: No idempotency key set — retry may cause duplicate charge"
        ),
        metadata_json=f'{{"gateway": "stripe", "http_status": 504, "order_id": "ORD-{order}", "has_idempotency_key": false}}',
    )


async def simulate_duplicate_charge():
    """BUG: Duplicate charge due to missing idempotency."""
    trace_id = str(uuid4())
    order = random.randint(10000, 99999)
    amount = round(random.uniform(50, 300), 2)
    await send_log(
        "CRITICAL",
        f"DUPLICATE CHARGE DETECTED for order #ORD-{order}! "
        f"Two successful charges of ${amount} found: "
        f"TXN-{random.randint(100000, 999999)} and TXN-{random.randint(100000, 999999)}. "
        "Root cause: retry after timeout did not use idempotency key. "
        "Customer will be double-charged. Immediate refund required.",
        trace_id=trace_id,
        stack_trace=(
            "Traceback (most recent call last):\n"
            '  File "payment_service/retry.py", line 33, in retry_charge\n'
            "    # BUG: should pass idempotency_key=original_request_id\n"
            "    result = await gateway.charge(amount=amount, currency='usd')\n"
            "    # Charge succeeded — but original also succeeded!\n"
            "DuplicateChargeError: Two successful charges for same order\n"
        ),
        metadata_json=f'{{"order_id": "ORD-{order}", "amount": {amount}, "duplicate_count": 2, "needs_refund": true}}',
    )


async def run_simulator():
    print(f"💳 {SERVICE_NAME} simulator started")
    scenarios = [
        (simulate_normal_operation, 0.5),
        (simulate_gateway_timeout, 0.3),
        (simulate_duplicate_charge, 0.2),
    ]
    while True:
        funcs, weights = zip(*scenarios)
        chosen = random.choices(funcs, weights=weights, k=1)[0]
        await chosen()
        await asyncio.sleep(random.uniform(3, 10))


if __name__ == "__main__":
    asyncio.run(run_simulator())
