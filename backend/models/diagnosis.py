"""ORM model and Pydantic schemas for diagnosis reports."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class DiagnosisStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


class ActionType(str, enum.Enum):
    READ = "read"
    WRITE = "write"


# ---------------------------------------------------------------------------
# ORM
# ---------------------------------------------------------------------------
class DiagnosisORM(Base):
    __tablename__ = "diagnoses"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    status: Mapped[str] = mapped_column(
        Enum(DiagnosisStatus), default=DiagnosisStatus.IN_PROGRESS
    )
    trigger_description: Mapped[str] = mapped_column(Text)
    reasoning_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    conclusion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action_type: Mapped[Optional[str]] = mapped_column(
        Enum(ActionType), nullable=True
    )


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class DiagnosisRequest(BaseModel):
    """Trigger a new diagnosis investigation."""

    description: str


class ReasoningStep(BaseModel):
    """A single step in the ReAct reasoning chain."""

    step_number: int
    thought: str
    action: Optional[str] = None
    action_input: Optional[str] = None
    observation: Optional[str] = None


class DiagnosisResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    created_at: datetime
    updated_at: datetime
    status: DiagnosisStatus
    trigger_description: str
    reasoning_trace: Optional[str] = None
    conclusion: Optional[str] = None
    evidence_ids: Optional[str] = None
    suggested_action: Optional[str] = None
    action_type: Optional[str] = None


class ActionApproval(BaseModel):
    """Human approval / rejection of a write action."""

    diagnosis_id: str
    approved: bool
    reviewer_notes: Optional[str] = None


class RecommendedActionRequest(BaseModel):
    """Persist a recommended action that awaits human approval."""

    diagnosis_id: str
    action_text: str
    action_type: ActionType = ActionType.WRITE
