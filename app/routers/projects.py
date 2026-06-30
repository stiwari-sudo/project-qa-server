from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.core.db import get_session
from app.schemas.project import ProjectOut
from app.services import project_members as members_service
from app.services import projects as projects_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: CurrentUser,
) -> list[ProjectOut]:
    visible = await members_service.visible_project_ids(session, user)
    return await projects_service.list_projects(session, visible_project_ids=visible)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: CurrentUser,
) -> ProjectOut:
    await members_service.assert_can_view_project(session, user, project_id)
    return await projects_service.get_project(session, project_id)
