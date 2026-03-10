"""Database startup tasks: migrations and seed data."""

import random
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from backend.models.diagnosis import DiagnosisORM, DiagnosisStatus


async def migrate_and_seed(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await _migrate_diagnosis_history(session_factory)
    await _seed_diagnoses_if_empty(session_factory)


async def _seed_diagnoses_if_empty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Seed initial diagnosis history with random states if none exist."""
    async with session_factory() as session:
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


async def _migrate_diagnosis_history(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Normalize legacy status values and ensure updated_at is populated."""
    async with session_factory() as session:
        await session.execute(
            text("UPDATE diagnoses SET status = 'rejected' " "WHERE status = 'failed'")
        )
        await session.execute(
            text(
                "UPDATE diagnoses SET updated_at = created_at "
                "WHERE updated_at IS NULL"
            )
        )
        await session.commit()
