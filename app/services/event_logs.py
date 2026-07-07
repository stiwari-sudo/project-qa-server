from __future__ import annotations

import csv
import io
import uuid
from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.event_log import Discipline, QaEventLog
from app.models.user import User
from app.repositories import event_logs as event_logs_repo
from app.repositories import projects as projects_repo
from app.schemas.event_log import (
    AnalysisBucket,
    EventLogAnalysis,
    EventLogCreate,
    EventLogOut,
    EventLogUpdate,
)
from app.services import project_members as members_service
from app.services.mappers import event_log_to_out


async def list_event_logs(
    session: AsyncSession,
    *,
    project_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    discipline: Discipline | None = None,
    logged_by_id: uuid.UUID | None = None,
    visible_project_ids: set[uuid.UUID] | None = None,
) -> list[EventLogOut]:
    rows = await event_logs_repo.list_filtered(
        session,
        project_id=project_id,
        stage_id=stage_id,
        discipline=discipline,
        logged_by_id=logged_by_id,
        visible_project_ids=visible_project_ids,
    )
    return [event_log_to_out(r) for r in rows]


async def create_event_log(
    session: AsyncSession, payload: EventLogCreate, user: User
) -> EventLogOut:
    project = await projects_repo.get_by_id(session, payload.project_id)
    if project is None:
        raise NotFoundError("Project not found")
    await members_service.assert_can_view_project(session, user, payload.project_id)

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
    session: AsyncSession, event_id: uuid.UUID, payload: EventLogUpdate, user: User
) -> EventLogOut:
    event = await event_logs_repo.get_by_id(session, event_id)
    if event is None:
        raise NotFoundError("Event log not found")
    await members_service.assert_can_view_project(session, user, event.project_id)

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, key, value)
    await session.flush()

    reloaded = await event_logs_repo.get_by_id(session, event_id)
    assert reloaded is not None
    return event_log_to_out(reloaded)


async def delete_event_log(
    session: AsyncSession, event_id: uuid.UUID, user: User
) -> None:
    event = await event_logs_repo.get_by_id(session, event_id)
    if event is None:
        raise NotFoundError("Event log not found")
    await members_service.assert_can_view_project(session, user, event.project_id)
    await event_logs_repo.delete(session, event)


def _buckets(counter: Counter[str]) -> list[AnalysisBucket]:
    return [
        AnalysisBucket(key=key, count=count)
        for key, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


async def analyse_event_logs(
    session: AsyncSession,
    *,
    project_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    discipline: Discipline | None = None,
    visible_project_ids: set[uuid.UUID] | None = None,
) -> EventLogAnalysis:
    rows = await event_logs_repo.list_filtered(
        session,
        project_id=project_id,
        stage_id=stage_id,
        discipline=discipline,
        visible_project_ids=visible_project_ids,
    )
    by_discipline: Counter[str] = Counter()
    by_category: Counter[str] = Counter()
    by_stage: Counter[str] = Counter()
    for r in rows:
        by_discipline[r.discipline.value] += 1
        by_category[r.category_of_impact] += 1
        by_stage[r.stage.name if r.stage else "Unassigned"] += 1
    return EventLogAnalysis(
        total=len(rows),
        by_discipline=_buckets(by_discipline),
        by_category=_buckets(by_category),
        by_stage=_buckets(by_stage),
    )


_EXPORT_COLUMNS = [
    "project_number",
    "project_name",
    "stage",
    "discipline",
    "category_of_impact",
    "description",
    "cause_reason",
    "action_effect",
    "logged_by",
    "created_at",
]


async def export_event_logs_csv(
    session: AsyncSession,
    *,
    project_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    discipline: Discipline | None = None,
    visible_project_ids: set[uuid.UUID] | None = None,
) -> str:
    rows = await event_logs_repo.list_filtered(
        session,
        project_id=project_id,
        stage_id=stage_id,
        discipline=discipline,
        visible_project_ids=visible_project_ids,
    )
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(
            {
                "project_number": r.project.number,
                "project_name": r.project.name,
                "stage": r.stage.name if r.stage else "",
                "discipline": r.discipline.value,
                "category_of_impact": r.category_of_impact,
                "description": r.description,
                "cause_reason": r.cause_reason or "",
                "action_effect": r.action_effect or "",
                "logged_by": r.logged_by.display_name if r.logged_by else "",
                "created_at": r.created_at.isoformat(),
            }
        )
    return buffer.getvalue()
