from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories import projects as projects_repo
from app.repositories import responses as responses_repo
from app.repositories import stages as stages_repo
from app.schemas.overview import (
    DirectorBucket,
    IncompleteProject,
    OverviewOut,
    OverviewTotals,
)

SITE_STAGE_ORDER = 5


@dataclass
class _Bucket:
    director_id: uuid.UUID | None
    director_name: str
    construction_project_count: int = 0
    calc_package_complete_count: int = 0
    incomplete_projects: list[IncompleteProject] = field(default_factory=list)


def _calc_pack_complete(responses: Mapping[str, Any], calc_ids: list[str]) -> bool:
    for qid in calc_ids:
        raw = responses.get(qid) or {}
        value = str(raw.get("value", "") if isinstance(raw, Mapping) else raw).strip().lower()
        if value and value not in ("no", "n/a", "na"):
            return True
    return False


async def build_overview(
    session: AsyncSession, director_id: uuid.UUID | None = None
) -> OverviewOut:
    projects = list(await projects_repo.list_active(session))
    if director_id is not None:
        projects = [p for p in projects if p.director_id == director_id]

    project_ids = [p.id for p in projects]
    all_responses = await responses_repo.list_for_projects(session, project_ids)

    construction_ids = await _construction_project_ids(session, projects, all_responses)

    merged_by_project: dict[uuid.UUID, dict[str, Any]] = {}
    for r in all_responses:
        if r.project_id in construction_ids:
            merged = merged_by_project.setdefault(r.project_id, {})
            merged.update(r.responses or {})

    calc_ids = settings.calc_pack_ids
    buckets: dict[str, _Bucket] = {}

    for p in projects:
        if p.id not in construction_ids:
            continue
        key = str(p.director_id) if p.director_id else "unassigned"
        bucket = buckets.get(key)
        if bucket is None:
            bucket = _Bucket(
                director_id=p.director_id,
                director_name=p.director.display_name if p.director else "Unassigned",
            )
            buckets[key] = bucket

        bucket.construction_project_count += 1
        if _calc_pack_complete(merged_by_project.get(p.id, {}), calc_ids):
            bucket.calc_package_complete_count += 1
        else:
            bucket.incomplete_projects.append(
                IncompleteProject(
                    project_id=p.id,
                    project_number=p.number,
                    project_name=p.name,
                    manager_name=p.manager.display_name if p.manager else None,
                )
            )

    director_out: list[DirectorBucket] = []
    for bucket in buckets.values():
        total = bucket.construction_project_count
        complete = bucket.calc_package_complete_count
        pct = round((complete / total) * 100, 1) if total else 0.0
        director_out.append(
            DirectorBucket(
                director_id=bucket.director_id,
                director_name=bucket.director_name,
                construction_project_count=total,
                calc_package_complete_count=complete,
                calc_package_completion_pct=pct,
                incomplete_projects=bucket.incomplete_projects,
            )
        )
    director_out.sort(key=lambda b: b.director_name)

    total_count = sum(b.construction_project_count for b in director_out)
    total_complete = sum(b.calc_package_complete_count for b in director_out)
    totals = OverviewTotals(
        construction_project_count=total_count,
        calc_package_complete_count=total_complete,
        calc_package_completion_pct=(
            round((total_complete / total_count) * 100, 1) if total_count else 0.0
        ),
    )
    return OverviewOut(directors=director_out, totals=totals)


async def _construction_project_ids(
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

    site_stage = await stages_repo.get_by_order(session, SITE_STAGE_ORDER)
    if site_stage is None:
        return set()
    return {
        r.project_id
        for r in all_responses
        if r.stage_id == site_stage.id and bool(r.responses)
    }
