from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories import projects as projects_repo
from app.schemas.project import ProjectOut
from app.services.mappers import project_to_out


async def list_projects(
    session: AsyncSession,
    *,
    visible_project_ids: set[uuid.UUID] | None = None,
) -> list[ProjectOut]:
    rows = await projects_repo.list_active(session)
    if visible_project_ids is not None:
        rows = [p for p in rows if p.id in visible_project_ids]
    return [project_to_out(p) for p in rows]


async def get_project(session: AsyncSession, project_id: uuid.UUID) -> ProjectOut:
    project = await projects_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError("Project not found")
    return project_to_out(project)
