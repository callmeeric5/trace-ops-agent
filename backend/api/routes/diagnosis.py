"""Diagnosis routes — trigger investigations, stream reasoning, approve actions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from backend.agent.graph import run_diagnosis
from backend.agent.guardrails import evaluate_action
from backend.db.database import get_db
from backend.models.diagnosis import (
    ActionApproval,
    RecommendedActionRequest,
    DiagnosisORM,
    DiagnosisRequest,
    DiagnosisResponse,
    DiagnosisStatus,
    ActionType,
)

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])


@router.post("/", status_code=201)
async def start_diagnosis(
    request: DiagnosisRequest,
    db: AsyncSession = Depends(get_db),
):
    """Start a new diagnostic investigation and return the diagnosis ID."""
    diagnosis = DiagnosisORM(
        id=str(uuid4()),
        trigger_description=request.description,
        status=DiagnosisStatus.IN_PROGRESS,
    )
    db.add(diagnosis)
    await db.flush()
    return {"diagnosis_id": diagnosis.id, "status": "in_progress"}


@router.get("/stream/{diagnosis_id}")
async def stream_diagnosis(diagnosis_id: str):
    """SSE endpoint — streams the agent's reasoning trace in real time.

    The client connects here after calling POST /diagnosis/ and receives
    a stream of JSON events as the agent thinks, acts, and observes.
    """

    async def event_generator():
        # Retrieve trigger description
        from backend.db.database import async_session_factory

        async with async_session_factory() as session:
            stmt = select(DiagnosisORM).where(DiagnosisORM.id == diagnosis_id)
            result = await session.execute(stmt)
            diagnosis = result.scalar_one_or_none()

        if not diagnosis:
            yield {
                "event": "error",
                "data": json.dumps({"error": "Diagnosis not found"}),
            }
            return

        async for step in run_diagnosis(
            description=diagnosis.trigger_description,
            diagnosis_id=diagnosis_id,
        ):
            yield {
                "event": step.get("type", "message"),
                "data": json.dumps(step, default=str),
            }

        # Investigation finished (leave status as-is unless awaiting approval)
        async with async_session_factory() as session:
            stmt = select(DiagnosisORM).where(DiagnosisORM.id == diagnosis_id)
            result = await session.execute(stmt)
            diag = result.scalar_one_or_none()
            if diag:
                diag.updated_at = datetime.now(timezone.utc)
                await session.commit()

    return EventSourceResponse(event_generator())


@router.get("/", response_model=list[DiagnosisResponse])
async def list_diagnoses(db: AsyncSession = Depends(get_db)):
    """List all diagnoses, newest first."""
    stmt = select(DiagnosisORM).order_by(DiagnosisORM.updated_at.desc()).limit(50)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{diagnosis_id}", response_model=DiagnosisResponse)
async def get_diagnosis(diagnosis_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single diagnosis by ID."""
    stmt = select(DiagnosisORM).where(DiagnosisORM.id == diagnosis_id)
    result = await db.execute(stmt)
    diag = result.scalar_one_or_none()
    if not diag:
        raise HTTPException(status_code=404, detail="Diagnosis not found")
    return diag


@router.post("/approve")
async def approve_action(
    approval: ActionApproval,
    db: AsyncSession = Depends(get_db),
):
    """Human approval / rejection of a write action suggested by the agent."""
    stmt = select(DiagnosisORM).where(DiagnosisORM.id == approval.diagnosis_id)
    result = await db.execute(stmt)
    diag = result.scalar_one_or_none()
    if not diag:
        raise HTTPException(status_code=404, detail="Diagnosis not found")

    if approval.approved:
        diag.status = DiagnosisStatus.APPROVED
        diag.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "approved", "message": "Action approved and will be executed."}
    else:
        diag.status = DiagnosisStatus.REJECTED
        diag.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "rejected", "message": "Action rejected by reviewer."}


@router.post("/recommended-action")
async def set_recommended_action(
    body: RecommendedActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Persist a recommended action that requires human approval."""
    stmt = select(DiagnosisORM).where(DiagnosisORM.id == body.diagnosis_id)
    result = await db.execute(stmt)
    diag = result.scalar_one_or_none()
    if not diag:
        raise HTTPException(status_code=404, detail="Diagnosis not found")

    diag.suggested_action = body.action_text
    diag.action_type = body.action_type
    diag.status = DiagnosisStatus.IN_PROGRESS
    diag.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {
        "status": "awaiting_approval",
        "diagnosis_id": diag.id,
        "action_type": diag.action_type or ActionType.WRITE,
    }


@router.post("/remind-later")
async def remind_later(
    approval: ActionApproval,
    db: AsyncSession = Depends(get_db),
):
    """Keep the investigation in progress without approving or rejecting."""
    stmt = select(DiagnosisORM).where(DiagnosisORM.id == approval.diagnosis_id)
    result = await db.execute(stmt)
    diag = result.scalar_one_or_none()
    if not diag:
        raise HTTPException(status_code=404, detail="Diagnosis not found")

    diag.status = DiagnosisStatus.AWAITING_APPROVAL
    diag.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "in_progress", "message": "Reminder set. Approval deferred."}


@router.post("/evaluate-action")
async def evaluate_proposed_action(body: dict):
    """Evaluate a proposed action through the guardrails engine."""
    action_text = body.get("action", "")
    verdict = evaluate_action(action_text)
    return {
        "allowed": verdict.allowed,
        "risk_level": verdict.risk_level.value,
        "reason": verdict.reason,
    }
