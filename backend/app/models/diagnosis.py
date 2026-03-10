"""
Pydantic models for diagnosis sessions.
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class DiagnosisStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    AWAITING_APPROVAL = "awaiting_approval"
    FAILED = "failed"


class ReasoningStep(BaseModel):
    """A single step in the agent's ReAct loop."""

    step_number: int
    thought: str = Field(..., description="Agent's reasoning / hypothesis")
    action: Optional[str] = Field(None, description="Tool the agent invoked")
    action_input: Optional[dict[str, Any]] = None
    observation: Optional[str] = Field(None, description="Result of the tool call")
    evidence_log_ids: list[str] = Field(default_factory=list, description="Log IDs supporting this step")


class DiagnosisReport(BaseModel):
    """Final diagnosis output from the agent."""

    diagnosis_id: str
    status: DiagnosisStatus
    summary: str = Field(..., description="Root cause summary")
    root_cause: Optional[str] = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    evidence: list[dict[str, Any]] = Field(default_factory=list, description="Evidence fragments with log_id anchors")
    reasoning_trace: list[ReasoningStep] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    created_at: str = ""
    completed_at: Optional[str] = None


class DiagnosisRequest(BaseModel):
    """Trigger a new diagnosis session."""

    alert_message: str = Field(..., description="The alert or symptom to investigate")
    service_hint: Optional[str] = Field(None, description="Optional service to focus on first")
    severity: str = Field(default="high", description="Alert severity: low, medium, high, critical")
