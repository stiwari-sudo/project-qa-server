from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_member import ProjectMember
from app.models.user import User


async def list_members(
    session: AsyncSession, project_id: uuid.UUID
) -> Sequence[User]:
    """Users granted visibility of a project, ordered by name."""
    result = await session.execute(
        select(User)
        .join(ProjectMember, ProjectMember.user_id == User.id)
        .where(ProjectMember.project_id == project_id)
        .order_by(User.display_name)
    )
    return result.scalars().all()


async def list_project_ids_for_user(
    session: AsyncSession, user_id: uuid.UUID
) -> list[uuid.UUID]:
    """Project ids the user is a member of (their visible set when own-only)."""
    result = await session.execute(
        select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
    )
    return list(result.scalars().all())


async def get(
    session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID
) -> ProjectMember | None:
    result = await session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def list_pairs(
    session: AsyncSession, source: str | None = None
) -> set[tuple[uuid.UUID, uuid.UUID]]:
    """(project_id, user_id) membership pairs — all of them, or only those from
    a given ``source``. The resourcing sync reconciles its own source and checks
    the full set so it never duplicates a manually-granted membership."""
    stmt = select(ProjectMember.project_id, ProjectMember.user_id)
    if source is not None:
        stmt = stmt.where(ProjectMember.source == source)
    result = await session.execute(stmt)
    return {(row.project_id, row.user_id) for row in result.all()}


async def add(
    session: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    source: str = "manual",
) -> ProjectMember:
    member = ProjectMember(project_id=project_id, user_id=user_id, source=source)
    session.add(member)
    await session.flush()
    return member


async def remove(
    session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    member = await get(session, project_id, user_id)
    if member is None:
        return False
    await session.delete(member)
    await session.flush()
    return True
