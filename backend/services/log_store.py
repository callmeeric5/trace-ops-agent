"""Log storage and query service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.log_entry import LogEntryCreate, LogEntryORM, LogLevel


class LogStore:
    """Handles all log persistence and retrieval operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ---- Write -----------------------------------------------------------

    async def insert(self, entry: LogEntryCreate) -> LogEntryORM:
        """Persist a single log entry and return the ORM instance."""
        orm = LogEntryORM(**entry.model_dump())
        self._session.add(orm)
        await self._session.flush()
        return orm

    async def insert_batch(self, entries: list[LogEntryCreate]) -> list[str]:
        """Persist multiple log entries. Returns the list of generated IDs."""
        orm_objects = [LogEntryORM(**e.model_dump()) for e in entries]
        self._session.add_all(orm_objects)
        await self._session.flush()
        return [o.id for o in orm_objects]

    # ---- Read ------------------------------------------------------------

    async def get_by_id(self, log_id: str) -> Optional[LogEntryORM]:
        result = await self._session.execute(
            select(LogEntryORM).where(LogEntryORM.id == log_id)
        )
        return result.scalar_one_or_none()

    async def query_logs(
        self,
        *,
        service: Optional[str] = None,
        level: Optional[LogLevel] = None,
        since_minutes: int = 60,
        keyword: Optional[str] = None,
        limit: int = 200,
    ) -> list[LogEntryORM]:
        """Flexible log query used by the Agent tools."""
        since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        stmt = select(LogEntryORM).where(LogEntryORM.timestamp >= since)

        if service:
            stmt = stmt.where(LogEntryORM.service == service)
        if level:
            stmt = stmt.where(LogEntryORM.level == level)
        if keyword:
            stmt = stmt.where(LogEntryORM.message.ilike(f"%{keyword}%"))

        stmt = stmt.order_by(LogEntryORM.timestamp.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_error_counts_by_service(
        self, since_minutes: int = 60
    ) -> list[dict]:
        """Aggregate error/critical counts grouped by service."""
        since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        stmt = (
            select(
                LogEntryORM.service,
                LogEntryORM.level,
                func.count().label("count"),
            )
            .where(LogEntryORM.timestamp >= since)
            .where(LogEntryORM.level.in_([LogLevel.ERROR, LogLevel.CRITICAL]))
            .group_by(LogEntryORM.service, LogEntryORM.level)
        )
        result = await self._session.execute(stmt)
        return [dict(row._mapping) for row in result.all()]

    async def get_recent_stack_traces(
        self, service: Optional[str] = None, limit: int = 20
    ) -> list[LogEntryORM]:
        """Fetch the most recent log entries that contain stack traces."""
        stmt = select(LogEntryORM).where(LogEntryORM.stack_trace.isnot(None))
        if service:
            stmt = stmt.where(LogEntryORM.service == service)
        stmt = stmt.order_by(LogEntryORM.timestamp.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
