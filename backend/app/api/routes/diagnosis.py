"""
Diagnosis routes — trigger and manage diagnosis sessions.
Wired to the LangGraph agent for real reasoning.
"""

import asyncio
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, BackgroundTasks

from app.models.diagnosis import DiagnosisRequest, DiagnosisReport, DiagnosisStatus
from app.agent.graph import run_diagnosis

logger = logging.getLogger("sentinel.diagnosis")
router = APIRouter(prefix="/api/v1/diagnosis", tags=["Diagnosis"])

# In-memory store for diagnosis sessions
_sessions: dict[str, dict] = {}


async def _run_diagnosis_task(diagnosis_id: str, alert_message: str, service_hint: str | None):
    """Background task that runs the agent."""
    try:
        _sessions[diagnosis_id]["status"] = "running"
        result = await run_diagnosis(diagnosis_id, alert_message, service_hint)
        _sessions[diagnosis_id].update(result)
        _sessions[diagnosis_id]["status"] = "completed"
        _sessions[diagnosis_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        logger.error(f"Diagnosis {diagnosis_id} failed: {exc}")
        _sessions[diagnosis_id]["status"] = "failed"
        _sessions[diagnosis_id]["error"] = str(exc)


@router.post("/", status_code=201)
async def create_diagnosis(request: DiagnosisRequest, background_tasks: BackgroundTasks):
    """
    Trigger a new diagnosis session.
    Kicks off the LangGraph agent in the background.
    Stream results via SSE at /api/v1/stream/{diagnosis_id}.
    """
    diagnosis_id = str(uuid.uuid4())

    _sessions[diagnosis_id] = {
        "diagnosis_id": diagnosis_id,
        "status": "starting",
        "summary": f"Investigating: {request.alert_message}",
        "alert_message": request.alert_message,
        "service_hint": request.service_hint,
        "severity": request.severity,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "reasoning_trace": [],
        "evidence_log_ids": [],
        "suggested_actions": [],
    }

    # Run the agent in the background
    background_tasks.add_task(
        _run_diagnosis_task, diagnosis_id, request.alert_message, request.service_hint
    )

    logger.info(f"Diagnosis session created: {diagnosis_id}")
    return {
        "diagnosis_id": diagnosis_id,
        "status": "starting",
        "stream_url": f"/api/v1/stream/{diagnosis_id}",
        "message": "Diagnosis session created. Connect to the stream URL for real-time updates.",
    }


@router.get("/")
async def list_diagnoses():
    """List all diagnosis sessions."""
    return {
        "sessions": [
            {
                "diagnosis_id": s["diagnosis_id"],
                "status": s["status"],
                "summary": s.get("summary", ""),
                "created_at": s.get("created_at", ""),
                "severity": s.get("severity", "high"),
            }
            for s in _sessions.values()
        ],
        "count": len(_sessions),
    }


@router.get("/{diagnosis_id}")
async def get_diagnosis(diagnosis_id: str):
    """Get the full diagnosis report including reasoning trace."""
    if diagnosis_id not in _sessions:
        raise HTTPException(status_code=404, detail="Diagnosis session not found")
    return _sessions[diagnosis_id]


@router.delete("/{diagnosis_id}")
async def cancel_diagnosis(diagnosis_id: str):
    """Cancel a running diagnosis session."""
    if diagnosis_id not in _sessions:
        raise HTTPException(status_code=404, detail="Diagnosis session not found")
    _sessions[diagnosis_id]["status"] = "failed"
    return {"status": "cancelled", "diagnosis_id": diagnosis_id}
