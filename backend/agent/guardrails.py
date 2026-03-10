"""Guardrails engine — enforces safety policies on agent actions.

Read operations (viewing logs, metrics) proceed automatically.
Write operations (restart pod, change config) require explicit human approval.
"""

import re
from dataclasses import dataclass
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"  # Read-only / observational
    MEDIUM = "medium"  # Reversible write
    HIGH = "high"  # Potentially destructive

    @property
    def requires_approval(self) -> bool:
        return self != RiskLevel.LOW


# Patterns that indicate a write / destructive action
_WRITE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\brestart\b", re.IGNORECASE),
    re.compile(r"\bscale\b", re.IGNORECASE),
    re.compile(r"\bdelete\b", re.IGNORECASE),
    re.compile(r"\brollback\b", re.IGNORECASE),
    re.compile(r"\bmodify\b", re.IGNORECASE),
    re.compile(r"\bupdate config\b", re.IGNORECASE),
    re.compile(r"\bkill\b", re.IGNORECASE),
    re.compile(r"\bdeploy\b", re.IGNORECASE),
]

_HIGH_RISK_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bdelete\b", re.IGNORECASE),
    re.compile(r"\brollback\b", re.IGNORECASE),
    re.compile(r"\bkill\b", re.IGNORECASE),
]


@dataclass(frozen=True)
class GuardrailVerdict:
    """Result of a guardrail check."""

    allowed: bool
    risk_level: RiskLevel
    reason: str


def evaluate_action(action_text: str) -> GuardrailVerdict:
    """Evaluate a proposed action and return a verdict.

    Parameters
    ----------
    action_text:
        Free-text description of the action the agent wants to perform.

    Returns
    -------
    GuardrailVerdict
    """
    # Check high-risk first
    for pattern in _HIGH_RISK_PATTERNS:
        if pattern.search(action_text):
            return GuardrailVerdict(
                allowed=False,
                risk_level=RiskLevel.HIGH,
                reason=(
                    f"Action blocked — matches high-risk pattern "
                    f"'{pattern.pattern}'.  Requires human approval."
                ),
            )

    for pattern in _WRITE_PATTERNS:
        if pattern.search(action_text):
            return GuardrailVerdict(
                allowed=False,
                risk_level=RiskLevel.MEDIUM,
                reason=(
                    f"Write action detected — matches pattern "
                    f"'{pattern.pattern}'.  Requires human approval."
                ),
            )

    return GuardrailVerdict(
        allowed=True,
        risk_level=RiskLevel.LOW,
        reason="Read-only action — proceeding automatically.",
    )
