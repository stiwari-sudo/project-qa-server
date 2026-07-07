from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.event_log import Discipline, QaEventLog

_LOAD = (
    selectinload(QaEventLog.project),
    selectinload(QaEventLog.stage),
    selectinload(QaEventLog.logged_by),
)


async def get_by_id(session: AsyncSession, event_id: uuid.UUID) -> QaEventLog | None:
    result = await session.execute(
        select(QaEventLog).where(QaEventLog.id == event_id).options(*_LOAD)
    )
    return result.scalar_one_or_none()


async def list_filtered(
    session: AsyncSession,
    *,
    project_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    discipline: Discipline | None = None,
    logged_by_id: uuid.UUID | None = None,
    visible_project_ids: set[uuid.UUID] | None = None,
) -> Sequence[QaEventLog]:
    stmt = select(QaEventLog).options(*_LOAD).order_by(QaEventLog.created_at.desc())
    # None = no restriction (view-all); an empty set correctly yields no rows.
    if visible_project_ids is not None:
        stmt = stmt.where(QaEventLog.project_id.in_(visible_project_ids))
    if logged_by_id is not None:
        stmt = stmt.where(QaEventLog.logged_by_id == logged_by_id)
    if project_id is not None:
        stmt = stmt.where(QaEventLog.project_id == project_id)
    if stage_id is not None:
        stmt = stmt.where(QaEventLog.stage_id == stage_id)
    if discipline is not None:
        stmt = stmt.where(QaEventLog.discipline == discipline)
    result = await session.execute(stmt)
    return result.scalars().all()


async def add(session: AsyncSession, event: QaEventLog) -> QaEventLog:
    session.add(event)
    await session.flush()
    loaded = await get_by_id(session, event.id)
    assert loaded is not None
    return loaded


async def delete(session: AsyncSession, event: QaEventLog) -> None:
    await session.delete(event)
    await session.flush()
