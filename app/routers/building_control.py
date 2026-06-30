from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_roles
from app.core.db import get_session
from app.models.user import User
from app.schemas.building_control import (
    BuildingControlList,
    BuildingControlOut,
    BuildingControlUpdate,
)
from app.services import building_control as bc_service

router = APIRouter(prefix="/building-control", tags=["building-control"])

# The Building Control register is a director oversight tool: reading the register
# (which exposes J: scan paths) and confirming/overriding both require a director.
# (The aggregate Building Control KPI on /overview stays open — it's counts only.)
_REQUIRE_DIRECTOR = require_roles("director", "founding_director", "admin")


@router.get("", response_model=BuildingControlList)
async def list_building_control(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(_REQUIRE_DIRECTOR)],
    director: uuid.UUID | None = None,
    project: uuid.UUID | None = None,
    status: str | None = None,  # "found" | "not_found" | "unknown" — filters items only
) -> BuildingControlList:
    return await bc_service.list_status(
        session, director_id=director, project_id=project, status=status
    )


@router.patch("/{project_id}", response_model=BuildingControlOut)
async def set_building_control(
    project_id: uuid.UUID,
    payload: BuildingControlUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(_REQUIRE_DIRECTOR)],
) -> BuildingControlOut:
    return await bc_service.set_manual(session, project_id, payload, user)
