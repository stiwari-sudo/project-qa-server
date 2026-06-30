from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.building import Building


async def list_for_project(
    session: AsyncSession, project_id: uuid.UUID
) -> Sequence[Building]:
    result = await session.execute(
        select(Building)
        .where(Building.project_id == project_id)
        .order_by(Building.order, Building.created_at)
    )
    return result.scalars().all()


async def get_by_id(
    session: AsyncSession, building_id: uuid.UUID
) -> Building | None:
    result = await session.execute(
        select(Building).where(Building.id == building_id)
    )
    return result.scalar_one_or_none()


async def get_primary_for_project(
    session: AsyncSession, project_id: uuid.UUID
) -> Building | None:
    """The project's primary building: lowest ``order``, then oldest. This is the
    implicit building that single-building projects use for all their QA."""
    result = await session.execute(
        select(Building)
        .where(Building.project_id == project_id)
        .order_by(Building.order, Building.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def add(session: AsyncSession, building: Building) -> Building:
    session.add(building)
    await session.flush()
    return building
