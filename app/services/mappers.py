"""ORM -> Pydantic output mappers (relations must be eager-loaded by the caller)."""

from __future__ import annotations

from app.models.event_log import QaEventLog
from app.models.hrb import QaHighRiskBuilding
from app.models.project import Project
from app.models.response import QaProjectResponse
from app.schemas.event_log import EventLogOut
from app.schemas.hrb import HrbOut
from app.schemas.project import ProjectOut
from app.schemas.response import ResponseOut


def project_to_out(p: Project) -> ProjectOut:
    return ProjectOut(
        id=p.id,
        number=p.number,
        name=p.name,
        sector=p.sector,
        archived=p.archived,
        director_id=p.director_id,
        director_name=p.director.display_name if p.director else None,
        manager_id=p.manager_id,
        manager_name=p.manager.display_name if p.manager else None,
        cmap_stage=p.cmap_stage,
    )


def response_to_out(pr: QaProjectResponse) -> ResponseOut:
    return ResponseOut(
        id=pr.id,
        project_id=pr.project_id,
        project_number=pr.project.number,
        project_name=pr.project.name,
        building_id=pr.building_id,
        building_name=pr.building.name,
        form_id=pr.form_id,
        form_name=pr.form.name,
        stage_id=pr.stage_id,
        stage_name=pr.stage.name,
        responses=pr.responses or {},
        completion_percentage=pr.completion_percentage,
        total_questions=pr.total_questions,
        answered_questions=pr.answered_questions,
        deadline=pr.deadline,
        reminder_sent_offsets=pr.reminder_sent_offsets or [],
        last_updated_by_id=pr.last_updated_by_id,
        last_updated_by_name=pr.last_updated_by.display_name if pr.last_updated_by else None,
        created_at=pr.created_at,
        updated_at=pr.updated_at,
    )


def event_log_to_out(e: QaEventLog) -> EventLogOut:
    return EventLogOut(
        id=e.id,
        project_id=e.project_id,
        project_number=e.project.number,
        project_name=e.project.name,
        description=e.description,
        cause_reason=e.cause_reason,
        action_effect=e.action_effect,
        category_of_impact=e.category_of_impact,
        stage_id=e.stage_id,
        stage_name=e.stage.name if e.stage else None,
        discipline=e.discipline,
        logged_by_id=e.logged_by_id,
        logged_by_name=e.logged_by.display_name if e.logged_by else None,
        created_at=e.created_at,
        updated_at=e.updated_at,
    )


def hrb_to_out(
    h: QaHighRiskBuilding, qa_completion_pct: float | None = None
) -> HrbOut:
    return HrbOut(
        id=h.id,
        project_id=h.project_id,
        project_number=h.project.number,
        project_name=h.project.name,
        building_id=h.building_id,
        building_name=h.building.name,
        manager_name=h.project.manager.display_name if h.project.manager else None,
        stage_id=h.stage_id,
        stage_name=h.stage.name if h.stage else None,
        qa_completion_pct=qa_completion_pct,
        is_high_risk=h.is_high_risk,
        checked_by_id=h.checked_by_id,
        checked_by_name=h.checked_by.display_name if h.checked_by else None,
        notes=h.notes,
        created_at=h.created_at,
        updated_at=h.updated_at,
    )
