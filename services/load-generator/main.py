"""
Load Generator — Continuously hits the mock services to generate realistic
logs with errors, latency spikes, and failures.

Run this as a standalone script or as a Docker service.
"""

import asyncio
import random
import logging
import sys

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger("load-generator")

API_GATEWAY_URL = "http://api-gateway:8001"


async def run_load(requests_per_second: int = 5, duration_seconds: int = 0):
    """
    Generate load against the mock services.
    
    Args:
        requests_per_second: Target RPS
        duration_seconds: How long to run (0 = forever)
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        total_requests = 0
        total_errors = 0

        logger.info(f"🔥 Starting load generator: {requests_per_second} RPS")

        while True:
            tasks = []

            for _ in range(requests_per_second):
                # Mix of different request types
                r = random.random()

                if r < 0.50:
                    # User lookup (may trigger pool leak, slow query, crash on id=13)
                    user_id = random.choice(list(range(1, 20)) + [13, 13])  # Weight id=13
                    tasks.append(client.get(f"{API_GATEWAY_URL}/api/users/{user_id}"))

                elif r < 0.80:
                    # Cache lookup (may trigger penetration, thundering herd)
                    key = random.choice(
                        [f"product:{random.randint(1, 20)}"] +  # Cache hits
                        [f"missing:{random.randint(100, 200)}"] * 3  # Cache misses (3x weight)
                    )
                    tasks.append(client.get(f"{API_GATEWAY_URL}/api/cache/{key}"))

                else:
                    # Health checks
                    tasks.append(client.get(f"{API_GATEWAY_URL}/health"))

            # Execute batch
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                total_requests += 1
                if isinstance(result, Exception):
                    total_errors += 1
                elif hasattr(result, "status_code") and result.status_code >= 400:
                    total_errors += 1

            error_rate = total_errors / total_requests if total_requests > 0 else 0
            if total_requests % 50 == 0:
                logger.info(
                    f"📊 Requests: {total_requests} | Errors: {total_errors} | "
                    f"Error Rate: {error_rate:.2%}"
                )

            if duration_seconds > 0 and total_requests >= requests_per_second * duration_seconds:
                break

            await asyncio.sleep(1.0)

    logger.info(f"✅ Load generation complete: {total_requests} requests, {total_errors} errors")


if __name__ == "__main__":
    rps = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    asyncio.run(run_load(rps, duration))
