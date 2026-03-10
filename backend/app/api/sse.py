"""
Server-Sent Events (SSE) streaming for real-time reasoning trace.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

logger = logging.getLogger("sentinel.sse")
router = APIRouter(prefix="/api/v1/stream", tags=["Streaming"])

# Global event bus — diagnosis_id → list of queued events
_event_queues: dict[str, asyncio.Queue] = {}


def get_event_queue(diagnosis_id: str) -> asyncio.Queue:
    """Get or create an event queue for a diagnosis session."""
    if diagnosis_id not in _event_queues:
        _event_queues[diagnosis_id] = asyncio.Queue()
    return _event_queues[diagnosis_id]


async def publish_event(diagnosis_id: str, event_type: str, data: dict):
    """Publish an event to all subscribers of a diagnosis session."""
    queue = get_event_queue(diagnosis_id)
    await queue.put({"event": event_type, "data": data})


async def _event_generator(diagnosis_id: str) -> AsyncGenerator[str, None]:
    """SSE event generator for a specific diagnosis session."""
    queue = get_event_queue(diagnosis_id)

    # Send initial connection event
    yield f"event: connected\ndata: {json.dumps({'diagnosis_id': diagnosis_id})}\n\n"

    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=30.0)
            event_type = event.get("event", "message")
            data = json.dumps(event.get("data", {}))
            yield f"event: {event_type}\ndata: {data}\n\n"

            # If diagnosis is complete, stop streaming
            if event_type in ("completed", "failed"):
                break
        except asyncio.TimeoutError:
            # Send keepalive
            yield f"event: keepalive\ndata: {json.dumps({'status': 'alive'})}\n\n"


@router.get("/{diagnosis_id}")
async def stream_diagnosis(diagnosis_id: str):
    """
    Stream real-time reasoning events for a diagnosis session.
    
    Event types:
      - connected: Initial connection
      - thought: Agent's reasoning step
      - action: Tool invocation
      - observation: Tool result
      - evidence: Log evidence found
      - approval_required: Write action needs approval
      - completed: Diagnosis finished
      - failed: Diagnosis failed
      - keepalive: Connection keepalive (every 30s)
    """
    return StreamingResponse(
        _event_generator(diagnosis_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
