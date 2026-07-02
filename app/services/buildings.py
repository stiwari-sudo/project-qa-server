from __future__ import annotations

import uuid

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.building import Building
from app.repositories import buildings as buildings_repo
from app.repositories import projects as projects_repo
from app.schemas.building import BuildingCreate, BuildingOut
from app.services import qa_folders


async def get_primary_building(
    session: AsyncSession, project_id: uuid.UUID
) -> Building:
    """Return the project's primary building, creating a default "Main building"
    if it has none. Self-healing so callers can always resolve a building for a
    project regardless of how the project was created."""
    primary = await buildings_repo.get_primary_for_project(session, project_id)
    if primary is not None:
        return primary
    if await projects_repo.get_by_id(session, project_id) is None:
        raise NotFoundError("Project not found")
    building = Building(project_id=project_id, name="Main building", order=0)
    return await buildings_repo.add(session, building)


async def resolve_building(
    session: AsyncSession,
    project_id: uuid.UUID,
    building_id: uuid.UUID | None = None,
) -> Building:
    """Resolve the building a QA operation targets. ``None`` means the project's
    primary building (the single-building case, where the UI shows no building
    picker); an explicit id must belong to the project."""
    if building_id is None:
        return await get_primary_building(session, project_id)
    building = await buildings_repo.get_by_id(session, building_id)
    if building is None or building.project_id != project_id:
        raise NotFoundError("Building not found for this project")
    return building


async def list_buildings(
    session: AsyncSession, project_id: uuid.UUID
) -> list[BuildingOut]:
    project = await projects_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError("Project not found")
    rows = await buildings_repo.list_for_project(session, project_id)
    return [BuildingOut.model_validate(r) for r in rows]


async def create_building(
    session: AsyncSession,
    project_id: uuid.UUID,
    payload: BuildingCreate,
    background_tasks: BackgroundTasks | None = None,
) -> BuildingOut:
    project = await projects_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError("Project not found")

    existing = await buildings_repo.list_for_project(session, project_id)
    order = (
        payload.order
        if payload.order is not None
        else max((b.order for b in existing), default=-1) + 1
    )
    building = Building(
        project_id=project_id, name=payload.name.strip(), order=order
    )
    created = await buildings_repo.add(session, building)

    # Scaffold this building's folders on the QA share — but only for buildings
    # added *beyond* the project's first (the primary/Main building keeps the
    # flat "10 QA" layout). Best-effort and off the request path; a no-op when no
    # share is configured (local dev).
    if background_tasks is not None and len(existing) >= 1:
        qa_folders.enqueue_building_folders(
            background_tasks, project.number, created.name
        )

    return BuildingOut.model_validate(created)
