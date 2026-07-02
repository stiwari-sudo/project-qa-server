from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.core.db import get_session
from app.models.event_log import Discipline
from app.schemas.event_log import (
    EventLogAnalysis,
    EventLogCreate,
    EventLogOut,
    EventLogUpdate,
)
from app.services import event_logs as event_logs_service
from app.services import project_members as members_service

router = APIRouter(prefix="/event-logs", tags=["event-logs"])

# Read access mirrors stats.py: an explicit ?project= is asserted, and the
# unscoped lists are filtered to the user's visible projects (None = view-all).


@router.get("", response_model=list[EventLogOut])
async def list_event_logs(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: CurrentUser,
    project: uuid.UUID | None = None,
    stage: uuid.UUID | None = None,
    discipline: Discipline | None = None,
) -> list[EventLogOut]:
    if project is not None:
        await members_service.assert_can_view_project(session, user, project)
    visible = await members_service.visible_project_ids(session, user)
    return await event_logs_service.list_event_logs(
        session,
        project_id=project,
        stage_id=stage,
        discipline=discipline,
        visible_project_ids=visible,
    )


@router.get("/analysis", response_model=EventLogAnalysis)
async def event_log_analysis(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: CurrentUser,
    project: uuid.UUID | None = None,
    stage: uuid.UUID | None = None,
    discipline: Discipline | None = None,
) -> EventLogAnalysis:
    if project is not None:
        await members_service.assert_can_view_project(session, user, project)
    visible = await members_service.visible_project_ids(session, user)
    return await event_logs_service.analyse_event_logs(
        session,
        project_id=project,
        stage_id=stage,
        discipline=discipline,
        visible_project_ids=visible,
    )


@router.get("/export")
async def export_event_logs(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: CurrentUser,
    project: uuid.UUID | None = None,
    stage: uuid.UUID | None = None,
    discipline: Discipline | None = None,
) -> Response:
    if project is not None:
        await members_service.assert_can_view_project(session, user, project)
    visible = await members_service.visible_project_ids(session, user)
    csv_text = await event_logs_service.export_event_logs_csv(
        session,
        project_id=project,
        stage_id=stage,
        discipline=discipline,
        visible_project_ids=visible,
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="event-logs.csv"'},
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
    user: CurrentUser,
) -> EventLogOut:
    return await event_logs_service.update_event_log(session, event_id, payload, user)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event_log(
    event_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: CurrentUser,
) -> Response:
    await event_logs_service.delete_event_log(session, event_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
