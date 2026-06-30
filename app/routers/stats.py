from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.core.db import get_session
from app.schemas.common import Paginated
from app.schemas.stats import AllProjectsStatsRow, ProjectStageStat
from app.services import project_members as members_service
from app.services import stats as stats_service

router = APIRouter(tags=["stats"])


@router.get("/projects/{project_id}/stats", response_model=list[ProjectStageStat])
async def project_stats(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: CurrentUser,
    building_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[ProjectStageStat]:
    await members_service.assert_can_view_project(session, user, project_id)
    return await stats_service.project_stats(session, project_id, building_id)


@router.get("/stats", response_model=Paginated[AllProjectsStatsRow])
async def all_projects_stats(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    search: str | None = None,
    director: uuid.UUID | None = None,
    manager: uuid.UUID | None = None,
    stage: str | None = None,
    status: str | None = None,
    scope: str | None = None,
) -> Paginated[AllProjectsStatsRow]:
    # scope=mine → the user's own assigned projects (any role). Otherwise the
    # role decides: view-all sees everything, engineers see their assignments.
    if scope == "mine":
        visible: set[uuid.UUID] | None = await members_service.member_project_ids(
            session, user
        )
    else:
        visible = await members_service.visible_project_ids(session, user)
    return await stats_service.all_projects_stats(
        session,
        page=page,
        page_size=page_size,
        search=search,
        director_id=director,
        manager_id=manager,
        stage=stage,
        status=status,
        visible_project_ids=visible,
    )
