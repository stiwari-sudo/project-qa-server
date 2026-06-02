from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.core.db import get_session
from app.schemas.project import ProjectOut
from app.services import projects as projects_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: CurrentUser,
) -> list[ProjectOut]:
    return await projects_service.list_projects(session)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: CurrentUser,
) -> ProjectOut:
    return await projects_service.get_project(session, project_id)
