"""ORM model and Pydantic schemas for log entries."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Enum, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class LogLevel(str, enum.Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogSource(str, enum.Enum):
    ORDER_SERVICE = "order-service"
    INVENTORY_SERVICE = "inventory-service"
    PAYMENT_SERVICE = "payment-service"
    SYSTEM = "system"


# ---------------------------------------------------------------------------
# SQLAlchemy ORM Model
# ---------------------------------------------------------------------------
class LogEntryORM(Base):
    __tablename__ = "log_entries"
    __table_args__ = (
        Index("ix_log_entries_service_level", "service", "level"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    service: Mapped[str] = mapped_column(String(64), index=True)
    level: Mapped[str] = mapped_column(Enum(LogLevel), default=LogLevel.INFO)
    message: Mapped[str] = mapped_column(Text)
    trace_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    span_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    stack_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Log {self.id[:8]} [{self.level}] {self.service}: {self.message[:40]}>"


# ---------------------------------------------------------------------------
# Pydantic Schemas (API boundary)
# ---------------------------------------------------------------------------
class LogEntryCreate(BaseModel):
    """Schema for ingesting a new log entry."""

    service: str
    level: LogLevel = LogLevel.INFO
    message: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    stack_trace: Optional[str] = None
    metadata_json: Optional[str] = None


class LogEntryResponse(BaseModel):
    """Schema returned to API consumers."""

    model_config = {"from_attributes": True}

    id: str
    timestamp: datetime
    service: str
    level: LogLevel
    message: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    stack_trace: Optional[str] = None
    metadata_json: Optional[str] = None


class LogBatchCreate(BaseModel):
    """Accept multiple log entries in a single request."""

    entries: list[LogEntryCreate] = Field(..., min_length=1, max_length=500)
