from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.core.db import get_session
from app.models.event_log import Discipline
from app.schemas.event_log import EventLogCreate, EventLogOut, EventLogUpdate
from app.services import event_logs as event_logs_service

router = APIRouter(prefix="/event-logs", tags=["event-logs"])


@router.get("", response_model=list[EventLogOut])
async def list_event_logs(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: CurrentUser,
    project: uuid.UUID | None = None,
    stage: uuid.UUID | None = None,
    discipline: Discipline | None = None,
) -> list[EventLogOut]:
    return await event_logs_service.list_event_logs(
        session, project_id=project, stage_id=stage, discipline=discipline
    )


@router.post("", response_model=EventLogOut, status_code=status.HTTP_201_CREATED)
async def create_event_log(
    payload: EventLogCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: CurrentUser,
) -> EventLogOut:
    return await event_logs_service.create_event_log(session, payload, user)


@router.patch("/{event_id}", response_model=EventLogOut)
async def update_event_log(
    event_id: uuid.UUID,
    payload: EventLogUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: CurrentUser,
) -> EventLogOut:
    return await event_logs_service.update_event_log(session, event_id, payload)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event_log(
    event_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: CurrentUser,
) -> Response:
    await event_logs_service.delete_event_log(session, event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
