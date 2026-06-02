from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.event_log import Discipline, QaEventLog
from app.models.user import User
from app.repositories import event_logs as event_logs_repo
from app.repositories import projects as projects_repo
from app.schemas.event_log import EventLogCreate, EventLogOut, EventLogUpdate
from app.services.mappers import event_log_to_out


async def list_event_logs(
    session: AsyncSession,
    *,
    project_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    discipline: Discipline | None = None,
) -> list[EventLogOut]:
    rows = await event_logs_repo.list_filtered(
        session, project_id=project_id, stage_id=stage_id, discipline=discipline
    )
    return [event_log_to_out(r) for r in rows]


async def create_event_log(
    session: AsyncSession, payload: EventLogCreate, user: User
) -> EventLogOut:
    project = await projects_repo.get_by_id(session, payload.project_id)
    if project is None:
        raise NotFoundError("Project not found")

    event = QaEventLog(
        project_id=payload.project_id,
        description=payload.description,
        cause_reason=payload.cause_reason,
        action_effect=payload.action_effect,
        category_of_impact=payload.category_of_impact,
        stage_id=payload.stage_id,
        discipline=payload.discipline,
        logged_by_id=user.id,
    )
    created = await event_logs_repo.add(session, event)
    return event_log_to_out(created)


async def update_event_log(
    session: AsyncSession, event_id: uuid.UUID, payload: EventLogUpdate
) -> EventLogOut:
    event = await event_logs_repo.get_by_id(session, event_id)
    if event is None:
        raise NotFoundError("Event log not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, key, value)
    await session.flush()

    reloaded = await event_logs_repo.get_by_id(session, event_id)
    assert reloaded is not None
    return event_log_to_out(reloaded)


async def delete_event_log(session: AsyncSession, event_id: uuid.UUID) -> None:
    event = await event_logs_repo.get_by_id(session, event_id)
    if event is None:
        raise NotFoundError("Event log not found")
    await event_logs_repo.delete(session, event)
