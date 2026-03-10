"""
Pydantic models for agent actions (guardrails).
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    READ = "read"       # Auto-approved (viewing logs, metrics)
    WRITE = "write"     # Requires human approval (restart pod, change config)


class ActionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"


class ProposedAction(BaseModel):
    """An action the agent wants to take."""

    action_id: str
    diagnosis_id: str
    action_type: ActionType
    description: str = Field(..., description="What the action will do")
    command: str = Field(..., description="Actual command / operation")
    risk_level: str = Field(default="medium", description="low, medium, high, critical")
    status: ActionStatus = ActionStatus.PENDING
    created_at: str = ""
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None


class ActionApproval(BaseModel):
    """Human approval / rejection of a proposed action."""

    action_id: str
    approved: bool
    approver: str = Field(default="admin")
    reason: Optional[str] = None
