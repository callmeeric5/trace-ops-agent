"""
Pydantic models for log entries.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class LogEntry(BaseModel):
    """A single log entry received from any service."""

    log_id: str = Field(..., description="Unique log identifier")
    timestamp: str = Field(..., description="ISO-8601 timestamp")
    service: str = Field(..., description="Source service name")
    level: str = Field(..., description="Log level: DEBUG, INFO, WARN, ERROR, CRITICAL")
    message: str = Field(..., description="Human-readable log message")

    # Optional structured fields
    stack_trace: Optional[str] = Field(None, description="Stack trace if present")
    extra: dict[str, Any] = Field(default_factory=dict, description="Additional context fields")

    class Config:
        json_schema_extra = {
            "example": {
                "log_id": "abc-123",
                "timestamp": "2026-03-10T12:00:00Z",
                "service": "user-service",
                "level": "ERROR",
                "message": "Connection pool exhausted",
                "stack_trace": None,
                "extra": {"pool_available": 0, "pool_leaked": 10},
            }
        }


class LogQueryParams(BaseModel):
    """Query parameters for filtering logs."""

    service: Optional[str] = None
    level: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    limit: int = Field(default=100, le=1000)
    search: Optional[str] = None


class LogStats(BaseModel):
    """Aggregate statistics for ingested logs."""

    total_logs: int
    by_service: dict[str, int]
    by_level: dict[str, int]
    latest_timestamp: Optional[str] = None
