from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.form import QaFormDefinition
from app.repositories import forms as forms_repo
from app.repositories import stages as stages_repo
from app.schemas.form import FormCreate, FormListItem, FormOut


def count_questions(structure: Mapping[str, Any]) -> int:
    """Count every question in the structure, including subform questions."""
    total = 0
    for section in structure.get("sections", []) or []:
        for question in section.get("questions", []) or []:
            total += _count_question(question)
    return total


def _count_question(question: Mapping[str, Any]) -> int:
    total = 1
    subform = question.get("subform")
    if subform:
        for sub_q in subform.get("questions", []) or []:
            total += _count_question(sub_q)
    return total


def _to_out(form: QaFormDefinition) -> FormOut:
    return FormOut.model_validate(
        {
            "id": form.id,
            "name": form.name,
            "version": form.version,
            "is_active": form.is_active,
            "stage_id": form.stage_id,
            "stage_name": form.stage.name,
            "structure": form.structure,
            "question_count": count_questions(form.structure),
            "created_at": form.created_at,
            "updated_at": form.updated_at,
        }
    )


async def list_active(session: AsyncSession) -> list[FormListItem]:
    forms = await forms_repo.list_active(session)
    return [
        FormListItem(
            id=f.id,
            name=f.name,
            version=f.version,
            is_active=f.is_active,
            stage_id=f.stage_id,
            stage_name=f.stage.name,
            question_count=count_questions(f.structure),
        )
        for f in forms
    ]


async def get_active_by_stage(session: AsyncSession, stage_id: uuid.UUID) -> FormOut:
    form = await forms_repo.get_active_by_stage(session, stage_id)
    if form is None:
        raise NotFoundError("No active form for this stage")
    return _to_out(form)


async def create_form(session: AsyncSession, payload: FormCreate) -> FormOut:
    stage = await stages_repo.get_by_id(session, payload.stage_id)
    if stage is None:
        raise NotFoundError("Stage not found")
    form = await forms_repo.create(
        session,
        name=payload.name,
        stage_id=payload.stage_id,
        version=payload.version,
        is_active=payload.is_active,
        structure=payload.structure.model_dump(),
    )
    return _to_out(form)
