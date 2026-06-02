from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stage import Stage


async def list_ordered(session: AsyncSession) -> Sequence[Stage]:
    result = await session.execute(select(Stage).order_by(Stage.order))
    return result.scalars().all()


async def get_by_id(session: AsyncSession, stage_id: uuid.UUID) -> Stage | None:
    return await session.get(Stage, stage_id)


async def get_by_order(session: AsyncSession, order: int) -> Stage | None:
    result = await session.execute(select(Stage).where(Stage.order == order))
    return result.scalar_one_or_none()
