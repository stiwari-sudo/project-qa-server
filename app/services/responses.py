from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.building import Building
from app.models.response import QaProjectResponse
from app.models.user import User
from app.repositories import forms as forms_repo
from app.repositories import responses as responses_repo
from app.repositories import stages as stages_repo
from app.schemas.response import BulkSaveIn, ResponseOut
from app.services import buildings as buildings_service
from app.services.hrb_sync import (
    find_building_hrb_answer,
    find_hrb_question_id,
    sync_hrb,
)
from app.services.mappers import response_to_out
from app.services.scoring import calculate_completion


async def get_or_create(
    session: AsyncSession,
    project_id: uuid.UUID,
    stage_id: uuid.UUID,
    building_id: uuid.UUID | None = None,
) -> ResponseOut:
    building = await buildings_service.resolve_building(session, project_id, building_id)
    pr = await responses_repo.get_for_building_stage(session, building.id, stage_id)
    if pr is None:
        pr = await _create_empty(session, building, stage_id)
    return response_to_out(pr)


async def list_for_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    building_id: uuid.UUID | None = None,
) -> list[ResponseOut]:
    building = await buildings_service.resolve_building(session, project_id, building_id)
    rows = await responses_repo.list_for_building(session, building.id)
    rows = sorted(rows, key=lambda r: r.stage.order)
    return [response_to_out(r) for r in rows]


async def bulk_save(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    stage_id: uuid.UUID,
    payload: BulkSaveIn,
    user: User,
    building_id: uuid.UUID | None = None,
) -> ResponseOut:
    building = await buildings_service.resolve_building(session, project_id, building_id)
    pr = await responses_repo.get_for_building_stage(session, building.id, stage_id)
    if pr is None:
        pr = await _create_empty(session, building, stage_id)

    # Deadline change resets the reminder idempotency tracker.
    if payload.deadline != pr.deadline:
        pr.deadline = payload.deadline
        pr.reminder_sent_offsets = []

    now = datetime.now(UTC).isoformat()
    merged = dict(pr.responses or {})
    for question_id, value in payload.responses.items():
        merged[question_id] = {
            "value": value,
            "responded_by_id": str(user.id),
            "responded_by_name": user.display_name,
            "timestamp": now,
        }
    pr.responses = merged
    pr.last_updated_by_id = user.id

    result = calculate_completion(pr.form.structure, merged)
    pr.completion_percentage = result.completion_percentage
    pr.total_questions = result.total_questions
    pr.answered_questions = result.answered_questions
    await session.flush()

    await sync_hrb(session, form=pr.form, response=pr, user=user)
    await session.flush()

    reloaded = await responses_repo.get_for_building_stage(session, building.id, stage_id)
    assert reloaded is not None
    return response_to_out(reloaded)


async def _create_empty(
    session: AsyncSession, building: Building, stage_id: uuid.UUID
) -> QaProjectResponse:
    stage = await stages_repo.get_by_id(session, stage_id)
    if stage is None:
        raise NotFoundError("Stage not found")
    form = await forms_repo.get_active_by_stage(session, stage_id)
    if form is None:
        raise NotFoundError("No active form for this stage")

    # Carry forward a Building-Safety-Act HRB determination already made on
    # another stage of this building: HRB status is a fact about the building, so
    # a stage opened for the first time inherits the answer (still editable, and
    # not flagged dirty since it matches what was loaded). Only when this stage's
    # form actually has the HRB question and a determination exists elsewhere.
    seeded: dict[str, Any] = {}
    hrb_qid = find_hrb_question_id(form.structure)
    if hrb_qid:
        carried = await find_building_hrb_answer(session, building.id)
        if carried is not None:
            seeded[hrb_qid] = {
                "value": carried.get("value"),
                "responded_by_id": carried.get("responded_by_id"),
                "responded_by_name": carried.get("responded_by_name"),
                "timestamp": carried.get("timestamp"),
            }

    pr = QaProjectResponse(
        project_id=building.project_id,
        building_id=building.id,
        form_id=form.id,
        stage_id=stage_id,
        responses=seeded,
    )
    if seeded:
        result = calculate_completion(form.structure, seeded)
        pr.completion_percentage = result.completion_percentage
        pr.total_questions = result.total_questions
        pr.answered_questions = result.answered_questions
    session.add(pr)
    await session.flush()
    reloaded = await responses_repo.get_for_building_stage(session, building.id, stage_id)
    assert reloaded is not None
    return reloaded
