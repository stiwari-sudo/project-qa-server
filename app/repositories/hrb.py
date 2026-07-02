from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.hrb import QaHighRiskBuilding
from app.models.project import Project

_LOAD = (
    selectinload(QaHighRiskBuilding.project).selectinload(Project.manager),
    selectinload(QaHighRiskBuilding.building),
    selectinload(QaHighRiskBuilding.stage),
    selectinload(QaHighRiskBuilding.checked_by),
)


async def get_by_id(session: AsyncSession, hrb_id: uuid.UUID) -> QaHighRiskBuilding | None:
    result = await session.execute(
        select(QaHighRiskBuilding).where(QaHighRiskBuilding.id == hrb_id).options(*_LOAD)
    )
    return result.scalar_one_or_none()


async def get_by_building_stage(
    session: AsyncSession, building_id: uuid.UUID, stage_id: uuid.UUID | None
) -> QaHighRiskBuilding | None:
    stmt = (
        select(QaHighRiskBuilding)
        .where(QaHighRiskBuilding.building_id == building_id)
        .options(*_LOAD)
    )
    if stage_id is None:
        stmt = stmt.where(QaHighRiskBuilding.stage_id.is_(None))
    else:
        stmt = stmt.where(QaHighRiskBuilding.stage_id == stage_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_filtered(
    session: AsyncSession,
    *,
    project_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    is_high_risk: bool | None = None,
    visible_project_ids: set[uuid.UUID] | None = None,
) -> Sequence[QaHighRiskBuilding]:
    stmt = (
        select(QaHighRiskBuilding)
        .options(*_LOAD)
        .order_by(QaHighRiskBuilding.created_at.desc())
    )
    # None = no restriction (view-all); an empty set correctly yields no rows.
    if visible_project_ids is not None:
        stmt = stmt.where(QaHighRiskBuilding.project_id.in_(visible_project_ids))
    if project_id is not None:
        stmt = stmt.where(QaHighRiskBuilding.project_id == project_id)
    if stage_id is not None:
        stmt = stmt.where(QaHighRiskBuilding.stage_id == stage_id)
    if is_high_risk is not None:
        stmt = stmt.where(QaHighRiskBuilding.is_high_risk.is_(is_high_risk))
    result = await session.execute(stmt)
    return result.scalars().all()


async def add(session: AsyncSession, hrb: QaHighRiskBuilding) -> QaHighRiskBuilding:
    session.add(hrb)
    await session.flush()
    loaded = await get_by_id(session, hrb.id)
    assert loaded is not None
    return loaded


async def delete(session: AsyncSession, hrb: QaHighRiskBuilding) -> None:
    await session.delete(hrb)
    await session.flush()
