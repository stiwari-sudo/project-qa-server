from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import projects as projects_repo
from app.repositories import responses as responses_repo
from app.repositories import stages as stages_repo
from app.schemas.common import Paginated
from app.schemas.stats import AllProjectsStatsRow, ProjectStageStat, StageCompletion
from app.services import buildings as buildings_service


def _stage_status(total: int, answered: int, pct: float) -> str:
    if answered <= 0:
        return "Not Started"
    if pct >= 100.0 or (total > 0 and answered >= total):
        return "Complete"
    return "In Progress"


async def project_stats(
    session: AsyncSession,
    project_id: uuid.UUID,
    building_id: uuid.UUID | None = None,
) -> list[ProjectStageStat]:
    # Per-stage breakdown for one building. ``building_id`` is optional — omit it
    # for single-building projects and the primary ("Main") building is used.
    building = await buildings_service.resolve_building(session, project_id, building_id)

    stages = await stages_repo.list_ordered(session)
    responses = await responses_repo.list_for_building(session, building.id)
    by_stage = {r.stage_id: r for r in responses}

    out: list[ProjectStageStat] = []
    for stage in stages:
        r = by_stage.get(stage.id)
        if r is None:
            out.append(
                ProjectStageStat(
                    stage_id=stage.id,
                    stage_name=stage.name,
                    stage_order=stage.order,
                    form_name=None,
                    form_version=None,
                    total_questions=0,
                    answered_questions=0,
                    completion_percentage=0.0,
                    last_updated=None,
                )
            )
            continue
        out.append(
            ProjectStageStat(
                stage_id=stage.id,
                stage_name=stage.name,
                stage_order=stage.order,
                form_name=r.form.name if r.form else None,
                form_version=r.form.version if r.form else None,
                total_questions=r.total_questions,
                answered_questions=r.answered_questions,
                completion_percentage=r.completion_percentage,
                last_updated=r.updated_at,
            )
        )
    return out


def _row_status(total_answered: int, completion_rate: float) -> str:
    if total_answered <= 0:
        return "Not Started"
    if completion_rate >= 100.0:
        return "Complete"
    return "In Progress"


async def all_projects_stats(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 25,
    search: str | None = None,
    director_id: uuid.UUID | None = None,
    manager_id: uuid.UUID | None = None,
    stage: str | None = None,
    status: str | None = None,
    visible_project_ids: set[uuid.UUID] | None = None,
) -> Paginated[AllProjectsStatsRow]:
    projects = list(await projects_repo.list_active(session))
    # Restrict to a caller-supplied allow-list (engineer's own projects, or a
    # "scope=mine" request). None means no restriction (view-all roles).
    if visible_project_ids is not None:
        projects = [p for p in projects if p.id in visible_project_ids]
    project_ids = [p.id for p in projects]
    responses = await responses_repo.list_for_projects(session, project_ids)

    responses_by_project: dict[uuid.UUID, list[Any]] = {}
    for r in responses:
        responses_by_project.setdefault(r.project_id, []).append(r)

    rows: list[AllProjectsStatsRow] = []
    for p in projects:
        prs = responses_by_project.get(p.id, [])

        stage_completion: dict[str, StageCompletion] = {}
        total_questions = 0
        total_answered = 0
        started_pcts: list[float] = []
        latest_order = -1
        latest_stage_name: str | None = None
        deadline: Any | None = None
        last_updated: datetime | None = None

        for r in prs:
            stage_name = r.stage.name
            stage_status = _stage_status(
                r.total_questions, r.answered_questions, r.completion_percentage
            )
            stage_completion[stage_name] = StageCompletion(
                stage_id=r.stage_id,
                stage_name=stage_name,
                stage_order=r.stage.order,
                total_questions=r.total_questions,
                answered_questions=r.answered_questions,
                completion_percentage=r.completion_percentage,
                status=stage_status,
            )

            total_questions += r.total_questions
            total_answered += r.answered_questions
            if r.answered_questions > 0:
                started_pcts.append(r.completion_percentage)
                if r.stage.order > latest_order:
                    latest_order = r.stage.order
                    latest_stage_name = stage_name

            if r.deadline is not None and (deadline is None or r.deadline < deadline):
                deadline = r.deadline
            if last_updated is None or r.updated_at > last_updated:
                last_updated = r.updated_at

        completion_rate = (
            round(sum(started_pcts) / len(started_pcts), 2) if started_pcts else 0.0
        )

        rows.append(
            AllProjectsStatsRow(
                project_id=p.id,
                project_number=p.number,
                project_name=p.name,
                director_id=p.director_id,
                director_name=p.director.display_name if p.director else None,
                manager_id=p.manager_id,
                manager_name=p.manager.display_name if p.manager else None,
                latest_qa_stage=latest_stage_name,
                cmap_stage=p.cmap_stage,
                total_questions=total_questions,
                total_answered=total_answered,
                completion_rate=completion_rate,
                status=_row_status(total_answered, completion_rate),
                deadline=deadline.isoformat() if deadline is not None else None,
                last_updated=last_updated,
                qa_stage_completion=stage_completion,
            )
        )

    rows = _apply_filters(
        rows,
        search=search,
        director_id=director_id,
        manager_id=manager_id,
        stage=stage,
        status=status,
    )
    rows.sort(key=lambda row: row.project_number)

    count = len(rows)
    page = max(page, 1)
    page_size = max(page_size, 1)
    total_pages = math.ceil(count / page_size) if count else 0
    start = (page - 1) * page_size
    paged = rows[start : start + page_size]

    return Paginated[AllProjectsStatsRow](
        count=count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        results=paged,
    )


def _apply_filters(
    rows: list[AllProjectsStatsRow],
    *,
    search: str | None,
    director_id: uuid.UUID | None,
    manager_id: uuid.UUID | None,
    stage: str | None,
    status: str | None,
) -> list[AllProjectsStatsRow]:
    out = rows
    if search:
        needle = search.strip().lower()
        out = [
            r
            for r in out
            if needle in r.project_number.lower() or needle in r.project_name.lower()
        ]
    if director_id is not None:
        out = [r for r in out if r.director_id == director_id]
    if manager_id is not None:
        out = [r for r in out if r.manager_id == manager_id]
    if stage:
        out = [r for r in out if r.latest_qa_stage == stage]
    if status:
        wanted = status.strip().lower()
        out = [r for r in out if r.status.lower() == wanted]
    return out
