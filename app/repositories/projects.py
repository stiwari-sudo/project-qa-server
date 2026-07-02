from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Project


async def get_by_id(session: AsyncSession, project_id: uuid.UUID) -> Project | None:
    result = await session.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.director), selectinload(Project.manager))
    )
    return result.scalar_one_or_none()


async def list_active(session: AsyncSession) -> Sequence[Project]:
    result = await session.execute(
        select(Project)
        .where(Project.archived.is_(False))
        .options(selectinload(Project.director), selectinload(Project.manager))
        .order_by(Project.number)
    )
    return result.scalars().all()


async def get_by_cmap_ref(session: AsyncSession, cmap_ref: str) -> Project | None:
    result = await session.execute(select(Project).where(Project.cmap_ref == cmap_ref))
    return result.scalar_one_or_none()


async def get_by_number(session: AsyncSession, number: str) -> Project | None:
    """First project with this number (number is indexed but not unique — used to
    link a not-yet-CMAP-reffed migrated project to its CMap record)."""
    result = await session.execute(
        select(Project).where(Project.number == number).order_by(Project.created_at)
    )
    return result.scalars().first()
