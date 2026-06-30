from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_roles
from app.core.db import get_session
from app.schemas.project_member import MemberAdd
from app.schemas.user import UserOut
from app.services import project_members as members_service

# Every admin route requires the "admin" role (router-level gate).
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_roles("admin"))],
)


@router.get(
    "/projects/{project_id}/members",
    response_model=list[UserOut],
)
async def list_project_members(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[UserOut]:
    return await members_service.list_members(session, project_id)


@router.post(
    "/projects/{project_id}/members",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_project_member(
    project_id: uuid.UUID,
    payload: MemberAdd,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserOut:
    return await members_service.add_member(session, project_id, payload.user_id)


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_project_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await members_service.remove_member(session, project_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
