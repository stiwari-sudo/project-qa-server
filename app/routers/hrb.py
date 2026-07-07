from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.core.db import get_session
from app.schemas.hrb import HrbCreate, HrbOut, HrbUpdate
from app.services import hrb as hrb_service
from app.services import project_members as members_service

router = APIRouter(prefix="/hrb", tags=["hrb"])


@router.get("", response_model=list[HrbOut])
async def list_hrb(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: CurrentUser,
    project: uuid.UUID | None = None,
    stage: uuid.UUID | None = None,
    is_high_risk: bool | None = None,
    mine: bool = False,
) -> list[HrbOut]:
    # mine=true: the personal "HRB determinations I recorded" view (any project).
    if mine:
        return await hrb_service.list_hrb(
            session,
            project_id=project,
            stage_id=stage,
            is_high_risk=is_high_risk,
            checked_by_id=user.id,
        )
    # Mirrors stats.py: explicit ?project= is asserted; the unscoped register
    # is filtered to the user's visible projects (None = view-all).
    if project is not None:
        await members_service.assert_can_view_project(session, user, project)
    visible = await members_service.visible_project_ids(session, user)
    return await hrb_service.list_hrb(
        session,
        project_id=project,
        stage_id=stage,
        is_high_risk=is_high_risk,
        visible_project_ids=visible,
    )


@router.post("", response_model=HrbOut, status_code=status.HTTP_201_CREATED)
async def create_hrb(
    payload: HrbCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: CurrentUser,
) -> HrbOut:
    return await hrb_service.upsert_hrb(session, payload, user)


@router.patch("/{hrb_id}", response_model=HrbOut)
async def update_hrb(
    hrb_id: uuid.UUID,
    payload: HrbUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: CurrentUser,
) -> HrbOut:
    return await hrb_service.update_hrb(session, hrb_id, payload, user)


@router.delete("/{hrb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_hrb(
    hrb_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: CurrentUser,
) -> Response:
    await hrb_service.delete_hrb(session, hrb_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
