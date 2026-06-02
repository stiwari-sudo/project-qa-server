from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.form import QaFormDefinition
from app.models.hrb import QaHighRiskBuilding
from app.models.response import QaProjectResponse
from app.models.user import User
from app.repositories import hrb as hrb_repo


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

    existing = await hrb_repo.get_by_project_stage(
        session, response.project_id, response.stage_id
    )
    if existing is None:
        session.add(
            QaHighRiskBuilding(
                project_id=response.project_id,
                stage_id=response.stage_id,
                is_high_risk=is_high_risk,
                checked_by_id=user.id,
            )
        )
    else:
        existing.is_high_risk = is_high_risk
        existing.checked_by_id = user.id
    await session.flush()
