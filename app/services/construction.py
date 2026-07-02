"""Shared "construction job" + calc-package helpers.

The director overview and the Building Control register agree on (a) which active
projects count as *construction* jobs and (b) the canonical "is the structural
calc package complete?" verdict, which is just the tracked ``q_*_sd_5`` form
answer. Keeping both here means the two surfaces can never drift.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories import stages as stages_repo

# Default stage order treated as "construction" by the site proxy (Site=5).
SITE_STAGE_ORDER = 5

# Calc-pack verdict (tri-state) derived from the form answer.
CALC_YES = "yes"
CALC_NO = "no"
CALC_BLANK = "blank"


def _value(raw: Any) -> str:
    if isinstance(raw, Mapping):
        raw = raw.get("value", "")
    return str(raw if raw is not None else "").strip().lower()


def calc_pack_status(merged: Mapping[str, Any], calc_ids: Sequence[str]) -> str:
    """Tri-state calc-pack verdict from the merged construction responses:
    ``yes`` if any tracked calc question is a Yes variant ("Yes", "Yes w/
    Evidence", …), else ``no`` if any is explicitly "No", else ``blank``. The
    Yes rule mirrors the legacy/overview "complete = any Yes" convention."""
    saw_no = False
    for qid in calc_ids:
        value = _value(merged.get(qid))
        if value.startswith("yes"):
            return CALC_YES
        if value == "no":
            saw_no = True
    return CALC_NO if saw_no else CALC_BLANK


def calc_pack_complete(merged: Mapping[str, Any], calc_ids: Sequence[str]) -> bool:
    """Whether the calc package is complete — the director KPI's Yes test."""
    return calc_pack_status(merged, calc_ids) == CALC_YES


async def construction_project_ids(
    session: AsyncSession,
    projects: Sequence[Any],
    all_responses: Sequence[Any],
) -> set[uuid.UUID]:
    """v1: Site-stage activity is the construction proxy. cmap: project.cmap_stage."""
    if settings.construction_source == "cmap":
        return {
            p.id
            for p in projects
            if p.cmap_stage and "construction" in p.cmap_stage.lower()
        }

    target_order = settings.construction_stage_order or SITE_STAGE_ORDER
    stage = await stages_repo.get_by_order(session, target_order)
    if stage is None:
        return set()
    return {
        r.project_id
        for r in all_responses
        if r.stage_id == stage.id and bool(r.responses)
    }


def merge_construction_responses(
    all_responses: Sequence[Any], construction_ids: set[uuid.UUID]
) -> dict[uuid.UUID, dict[str, Any]]:
    """Flatten every construction-stage response of each construction job into one
    answer map per project (later stages win on key collisions)."""
    merged: dict[uuid.UUID, dict[str, Any]] = {}
    for r in all_responses:
        if r.project_id in construction_ids:
            merged.setdefault(r.project_id, {}).update(r.responses or {})
    return merged
