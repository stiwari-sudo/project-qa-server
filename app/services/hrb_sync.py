from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.form import QaFormDefinition
from app.models.hrb import QaHighRiskBuilding
from app.models.response import QaProjectResponse
from app.models.user import User
from app.repositories import hrb as hrb_repo
from app.repositories import responses as responses_repo


def find_hrb_question_id(structure: Mapping[str, Any]) -> str | None:
    """Return the id of the question flagged hrb_flag=true (searches subforms too)."""
    for section in structure.get("sections", []) or []:
        for question in section.get("questions", []) or []:
            found = _scan(question)
            if found:
                return found
    return None


def _scan(question: Mapping[str, Any]) -> str | None:
    if question.get("hrb_flag"):
        return str(question.get("id", "")) or None
    subform = question.get("subform")
    if subform:
        for sub_q in subform.get("questions", []) or []:
            found = _scan(sub_q)
            if found:
                return found
    return None


def _latest_hrb_cell(
    forms_and_responses: list[tuple[Mapping[str, Any], Mapping[str, Any]]],
) -> dict[str, Any] | None:
    """Pick the most recent *answered* Building-Safety-Act HRB cell from
    (form structure, responses) pairs — skipping forms without the HRB question
    and blank answers, breaking ties by latest ISO timestamp. Pure (no DB) so
    the carry-forward selection rule is unit-testable.
    """
    best_ts = ""
    best_cell: dict[str, Any] | None = None
    for structure, responses in forms_and_responses:
        qid = find_hrb_question_id(structure)
        if not qid:
            continue
        cell = (responses or {}).get(qid)
        if not isinstance(cell, Mapping):
            continue
        if not str(cell.get("value", "")).strip():
            continue
        ts = str(cell.get("timestamp", "") or "")
        if best_cell is None or ts >= best_ts:
            best_ts = ts
            best_cell = dict(cell)
    return best_cell


async def find_building_hrb_answer(
    session: AsyncSession, building_id: uuid.UUID
) -> dict[str, Any] | None:
    """Return a building's most recent Building-Safety-Act HRB answer cell across
    all of its stages, or None if no determination has been made yet.

    An HRB status is a fact about the building, not a single QA stage, so a stage
    that hasn't been answered yet can carry forward the answer already recorded on
    another stage of the same building.
    """
    rows = await responses_repo.list_for_building(session, building_id)
    return _latest_hrb_cell([(r.form.structure, r.responses or {}) for r in rows])


async def sync_hrb(
    session: AsyncSession,
    *,
    form: QaFormDefinition,
    response: QaProjectResponse,
    user: User,
) -> None:
    """Mirror the Building-Safety-Act HRB answer into the QaHighRiskBuilding table."""
    qid = find_hrb_question_id(form.structure)
    if not qid:
        return

    raw = (response.responses or {}).get(qid) or {}
    value = str(raw.get("value", "") if isinstance(raw, Mapping) else raw).strip().lower()
    is_high_risk = value == "yes"

    existing = await hrb_repo.get_by_building_stage(
        session, response.building_id, response.stage_id
    )
    if existing is None:
        session.add(
            QaHighRiskBuilding(
                project_id=response.project_id,
                building_id=response.building_id,
                stage_id=response.stage_id,
                is_high_risk=is_high_risk,
                checked_by_id=user.id,
            )
        )
    else:
        existing.is_high_risk = is_high_risk
        existing.checked_by_id = user.id
    await session.flush()
