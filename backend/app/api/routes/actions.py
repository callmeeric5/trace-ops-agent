"""
Action routes — guardrails for agent-proposed actions.

Killer Feature #3: Safety Guardrails
  - READ operations (logs, metrics) → auto-approved
  - WRITE operations (restart pod, change config) → require human approval
"""

import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.models.action import (
    ProposedAction,
    ActionApproval,
    ActionStatus,
    ActionType,
)

logger = logging.getLogger("sentinel.actions")
router = APIRouter(prefix="/api/v1/actions", tags=["Actions"])

# In-memory store
_actions: dict[str, ProposedAction] = {}


@router.post("/propose", status_code=201)
async def propose_action(action: ProposedAction):
    """
    Agent proposes an action. READ actions are auto-approved;
    WRITE actions enter PENDING state awaiting human approval.
    """
    action.action_id = str(uuid.uuid4())
    action.created_at = datetime.now(timezone.utc).isoformat()

    if action.action_type == ActionType.READ:
        action.status = ActionStatus.APPROVED
        logger.info(f"READ action auto-approved: {action.description}")
    else:
        action.status = ActionStatus.PENDING
        logger.info(f"WRITE action pending approval: {action.description}")

    _actions[action.action_id] = action
    return action


@router.get("/")
async def list_actions():
    """List all proposed actions."""
    return {"actions": list(_actions.values()), "count": len(_actions)}


@router.get("/pending")
async def list_pending_actions():
    """List actions awaiting human approval."""
    pending = [a for a in _actions.values() if a.status == ActionStatus.PENDING]
    return {"actions": pending, "count": len(pending)}


@router.post("/approve")
async def approve_action(approval: ActionApproval):
    """Human approves or rejects a proposed action."""
    if approval.action_id not in _actions:
        raise HTTPException(status_code=404, detail="Action not found")

    action = _actions[approval.action_id]
    if action.status != ActionStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Action is not pending (status: {action.status})")

    if approval.approved:
        action.status = ActionStatus.APPROVED
        action.approved_by = approval.approver
        action.approved_at = datetime.now(timezone.utc).isoformat()
        logger.info(f"Action {action.action_id} APPROVED by {approval.approver}")
    else:
        action.status = ActionStatus.REJECTED
        logger.info(f"Action {action.action_id} REJECTED by {approval.approver}")

    return action
