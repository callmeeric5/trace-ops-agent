"""Persistent memory for the diagnostic agent.

Stores investigation chains so the agent avoids circular reasoning across
multiple runs.  Uses SQLite for simplicity; swap for Redis/PostgreSQL in
production.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base
from backend.db.database import async_session_factory


class InvestigationMemoryORM(Base):
    __tablename__ = "investigation_memory"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    diagnosis_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    step_type: Mapped[str] = mapped_column(String(32))  # thought / action / observation
    content: Mapped[str] = mapped_column(Text)


class AgentMemory:
    """Read/write memory for an ongoing investigation."""

    def __init__(self, diagnosis_id: str) -> None:
        self.diagnosis_id = diagnosis_id

    async def append(self, step_type: str, content: str) -> None:
        """Persist a reasoning step."""
        async with async_session_factory() as session:
            entry = InvestigationMemoryORM(
                diagnosis_id=self.diagnosis_id,
                step_type=step_type,
                content=content,
            )
            session.add(entry)
            await session.commit()

    async def get_history(self) -> list[dict]:
        """Return the full reasoning chain for this diagnosis."""
        async with async_session_factory() as session:
            stmt = (
                select(InvestigationMemoryORM)
                .where(InvestigationMemoryORM.diagnosis_id == self.diagnosis_id)
                .order_by(InvestigationMemoryORM.created_at)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [
            {
                "step_type": r.step_type,
                "content": r.content,
                "timestamp": r.created_at.isoformat(),
            }
            for r in rows
        ]

    async def has_investigated(self, action_signature: str) -> bool:
        """Check if this exact action was already performed (loop guard)."""
        async with async_session_factory() as session:
            stmt = (
                select(InvestigationMemoryORM)
                .where(InvestigationMemoryORM.diagnosis_id == self.diagnosis_id)
                .where(InvestigationMemoryORM.step_type == "action")
                .where(InvestigationMemoryORM.content == action_signature)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None
