"""Database engine and session management."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select, func, text

from backend.config import get_settings
from backend.db.base import Base
from backend.models.diagnosis import DiagnosisORM, DiagnosisStatus

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:  # type: ignore[misc]
    """Yield a database session for dependency injection."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables — used during application startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await _migrate_diagnosis_history()
    await _seed_diagnoses_if_empty()


async def _seed_diagnoses_if_empty() -> None:
    """Seed initial diagnosis history with random states if none exist."""
    async with async_session_factory() as session:
        result = await session.execute(select(func.count()).select_from(DiagnosisORM))
        count = result.scalar_one()
        if count and count > 0:
            return

        statuses = [
            DiagnosisStatus.IN_PROGRESS,
            DiagnosisStatus.APPROVED,
            DiagnosisStatus.REJECTED,
            DiagnosisStatus.AWAITING_APPROVAL,
        ]
        now = datetime.now(timezone.utc)
        samples = []
        for i in range(6):
            created_at = now - timedelta(minutes=random.randint(5, 180))
            status = random.choice(statuses)
            samples.append(
                DiagnosisORM(
                    trigger_description=f"Seeded investigation #{i + 1}",
                    status=status,
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
        session.add_all(samples)
        await session.commit()


async def _migrate_diagnosis_history() -> None:
    """Normalize legacy status values and ensure updated_at is populated."""
    async with async_session_factory() as session:
        await session.execute(
            text(
                "UPDATE diagnoses SET status = 'rejected' "
                "WHERE status = 'failed'"
            )
        )
        await session.execute(
            text(
                "UPDATE diagnoses SET updated_at = created_at "
                "WHERE updated_at IS NULL"
            )
        )
        await session.commit()
