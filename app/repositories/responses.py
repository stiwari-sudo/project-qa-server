from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Project
from app.models.response import QaProjectResponse

_FULL_LOAD = (
    selectinload(QaProjectResponse.project).selectinload(Project.director),
    selectinload(QaProjectResponse.project).selectinload(Project.manager),
    selectinload(QaProjectResponse.building),
    selectinload(QaProjectResponse.form),
    selectinload(QaProjectResponse.stage),
    selectinload(QaProjectResponse.last_updated_by),
)


async def get_for_building_stage(
    session: AsyncSession, building_id: uuid.UUID, stage_id: uuid.UUID
) -> QaProjectResponse | None:
    result = await session.execute(
        select(QaProjectResponse)
        .where(
            QaProjectResponse.building_id == building_id,
            QaProjectResponse.stage_id == stage_id,
        )
        .options(*_FULL_LOAD)
    )
    return result.scalar_one_or_none()


async def list_for_building(
    session: AsyncSession, building_id: uuid.UUID
) -> Sequence[QaProjectResponse]:
    result = await session.execute(
        select(QaProjectResponse)
        .where(QaProjectResponse.building_id == building_id)
        .options(*_FULL_LOAD)
    )
    return result.scalars().all()


async def list_for_project(
    session: AsyncSession, project_id: uuid.UUID
) -> Sequence[QaProjectResponse]:
    """All responses across every building of a project — for project-level
    dashboards (stats, overview) that roll up across buildings."""
    result = await session.execute(
        select(QaProjectResponse)
        .where(QaProjectResponse.project_id == project_id)
        .options(*_FULL_LOAD)
    )
    return result.scalars().all()


async def list_for_projects(
    session: AsyncSession, project_ids: list[uuid.UUID]
) -> Sequence[QaProjectResponse]:
    if not project_ids:
        return []
    result = await session.execute(
        select(QaProjectResponse)
        .where(QaProjectResponse.project_id.in_(project_ids))
        .options(selectinload(QaProjectResponse.stage))
    )
    return result.scalars().all()
