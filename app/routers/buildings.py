from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.core.db import get_session
from app.schemas.building import BuildingCreate, BuildingOut
from app.services import buildings as buildings_service

router = APIRouter(prefix="/projects", tags=["buildings"])


@router.get("/{project_id}/buildings", response_model=list[BuildingOut])
async def list_project_buildings(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: CurrentUser,
) -> list[BuildingOut]:
    return await buildings_service.list_buildings(session, project_id)


@router.post(
    "/{project_id}/buildings",
    response_model=BuildingOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_building(
    project_id: uuid.UUID,
    payload: BuildingCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: CurrentUser,
) -> BuildingOut:
    return await buildings_service.create_building(session, project_id, payload)
