from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories import building_control as bc_repo
from app.repositories import projects as projects_repo
from app.repositories import responses as responses_repo
from app.repositories import stages as stages_repo
from app.schemas.overview import (
    AnalysisTotals,
    BasicQaCheck,
    DirectorAnalysisRow,
    DirectorBucket,
    DirectorCompletion,
    IncompleteProject,
    OverviewOut,
    OverviewTotals,
    StageCount,
)
from app.services import building_control as bc_service
from app.services import construction

# Stage-distribution buckets for projects with no qualifying activity.
NO_QA_STARTED = "No QA Started"
NOT_SYNCED = "Not synced"
# Long-tail bucket for the dirty free-text legacy CMAP stage values.
CMAP_OTHER = "Other"
CMAP_TOP_N = 10


@dataclass
class _Bucket:
    director_id: uuid.UUID | None
    director_name: str
    construction_project_count: int = 0
    calc_package_complete_count: int = 0
    incomplete_projects: list[IncompleteProject] = field(default_factory=list)


@dataclass
class _CompBucket:
    director_id: uuid.UUID | None
    director_name: str
    project_count: int = 0
    pct_sum: float = 0.0


@dataclass
class _AnalysisBucket:
    director_id: uuid.UUID | None
    director_name: str
    total_projects: int = 0
    has_responses: int = 0
    completion_sum: float = 0.0
    qa_stage_counts: dict[str, int] = field(default_factory=dict)
    cmap_stage_counts: dict[str, int] = field(default_factory=dict)


def _has_yes_answer(responses_json: Mapping[str, Any]) -> bool:
    """Legacy "Basic QA Check" rule: a project has responded once any answer is
    a "Yes" variant ("Yes", "Yes w/ Evidence", "Yes w/o Evidence", …). Mirrors
    the legacy ``action_id in {1, 2}`` check; No / N/A / blank / placeholder
    dashes ("----------") do not count. Same Yes convention as the calc-pack check."""
    for raw in responses_json.values():
        value = str(raw.get("value", "") if isinstance(raw, Mapping) else raw).strip().lower()
        if value.startswith("yes"):
            return True
    return False


def _project_completion(responses: Sequence[Any]) -> float:
    """Mean of a project's *started* stage completion percentages — mirrors the
    per-project completion shown on the projects list (0.0 if none started)."""
    started = [r.completion_percentage for r in responses if r.answered_questions > 0]
    return sum(started) / len(started) if started else 0.0


async def build_overview(
    session: AsyncSession, director_id: uuid.UUID | None = None
) -> OverviewOut:
    projects = list(await projects_repo.list_active(session))
    if director_id is not None:
        projects = [p for p in projects if p.director_id == director_id]

    project_ids = [p.id for p in projects]
    all_responses = await responses_repo.list_for_projects(session, project_ids)

    construction_ids = await construction.construction_project_ids(
        session, projects, all_responses
    )
    merged_by_project = construction.merge_construction_responses(
        all_responses, construction_ids
    )

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
        if construction.calc_pack_complete(merged_by_project.get(p.id, {}), calc_ids):
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

    # Detailed QA: average per-project completion across ALL active projects,
    # grouped by director (every stage, not just construction).
    responses_by_project: dict[uuid.UUID, list[Any]] = {}
    for r in all_responses:
        responses_by_project.setdefault(r.project_id, []).append(r)

    comp_buckets: dict[str, _CompBucket] = {}
    for p in projects:
        key = str(p.director_id) if p.director_id else "unassigned"
        comp = comp_buckets.get(key)
        if comp is None:
            comp = _CompBucket(
                director_id=p.director_id,
                director_name=p.director.display_name if p.director else "Unassigned",
            )
            comp_buckets[key] = comp
        comp.project_count += 1
        comp.pct_sum += _project_completion(responses_by_project.get(p.id, []))

    completion_by_director = [
        DirectorCompletion(
            director_id=comp.director_id,
            director_name=comp.director_name,
            project_count=comp.project_count,
            avg_completion_pct=(
                round(comp.pct_sum / comp.project_count, 1) if comp.project_count else 0.0
            ),
        )
        for comp in comp_buckets.values()
    ]
    completion_by_director.sort(key=lambda c: c.director_name)

    # Director Analysis (ported from legacy): per-director response rate
    # (Basic QA Check), average completion, and QA + CMAP stage distributions.
    stages = await stages_repo.list_ordered(session)
    stage_order = {s.name: s.order for s in stages}

    project_has_yes: set[uuid.UUID] = set()
    project_latest_yes_stage: dict[uuid.UUID, tuple[int, str]] = {}
    for r in all_responses:
        if _has_yes_answer(r.responses or {}):
            project_has_yes.add(r.project_id)
            current = project_latest_yes_stage.get(r.project_id)
            if current is None or r.stage.order > current[0]:
                project_latest_yes_stage[r.project_id] = (r.stage.order, r.stage.name)

    analysis_buckets: dict[str, _AnalysisBucket] = {}
    for p in projects:
        key = str(p.director_id) if p.director_id else "unassigned"
        ab = analysis_buckets.get(key)
        if ab is None:
            ab = _AnalysisBucket(
                director_id=p.director_id,
                director_name=p.director.display_name if p.director else "Unassigned",
            )
            analysis_buckets[key] = ab

        ab.total_projects += 1
        ab.completion_sum += _project_completion(responses_by_project.get(p.id, []))
        if p.id in project_has_yes:
            ab.has_responses += 1
            qa_stage = project_latest_yes_stage[p.id][1]
        else:
            qa_stage = NO_QA_STARTED
        ab.qa_stage_counts[qa_stage] = ab.qa_stage_counts.get(qa_stage, 0) + 1

        cmap = p.cmap_stage.strip() if p.cmap_stage and p.cmap_stage.strip() else NOT_SYNCED
        ab.cmap_stage_counts[cmap] = ab.cmap_stage_counts.get(cmap, 0) + 1

    director_analysis: list[DirectorAnalysisRow] = []
    agg_qa_counts: dict[str, int] = {}
    agg_cmap_counts: dict[str, int] = {}
    for ab in analysis_buckets.values():
        no_responses = ab.total_projects - ab.has_responses
        rate = (
            round(ab.has_responses / ab.total_projects * 100, 1)
            if ab.total_projects
            else 0.0
        )
        completion = (
            round(ab.completion_sum / ab.total_projects, 1) if ab.total_projects else 0.0
        )
        director_analysis.append(
            DirectorAnalysisRow(
                director_id=ab.director_id,
                director_name=ab.director_name,
                total_projects=ab.total_projects,
                basic_qa_check=BasicQaCheck(
                    has_responses=ab.has_responses,
                    no_responses=no_responses,
                    response_rate=rate,
                ),
                completion_rate=completion,
                qa_stage_distribution=_qa_stage_counts_to_list(ab.qa_stage_counts, stage_order),
                cmap_stage_distribution=_cmap_stage_counts_to_list(ab.cmap_stage_counts),
            )
        )
        for name, count in ab.qa_stage_counts.items():
            agg_qa_counts[name] = agg_qa_counts.get(name, 0) + count
        for name, count in ab.cmap_stage_counts.items():
            agg_cmap_counts[name] = agg_cmap_counts.get(name, 0) + count
    director_analysis.sort(key=lambda d: d.director_name)

    total_has = sum(d.basic_qa_check.has_responses for d in director_analysis)
    total_projects_a = sum(d.total_projects for d in director_analysis)
    completion_sum_all = sum(ab.completion_sum for ab in analysis_buckets.values())
    analysis_totals = AnalysisTotals(
        total_directors=sum(1 for ab in analysis_buckets.values() if ab.director_id),
        total_projects=total_projects_a,
        has_responses=total_has,
        no_responses=total_projects_a - total_has,
        response_rate=(
            round(total_has / total_projects_a * 100, 1) if total_projects_a else 0.0
        ),
        avg_completion_rate=(
            round(completion_sum_all / total_projects_a, 1) if total_projects_a else 0.0
        ),
    )

    # Building Control / calc-pack coverage across the same construction jobs:
    # the form verdict spread plus how well the advisory J: scan agrees with it.
    scan_by_project = {r.project_id: r for r in await bc_repo.list_all(session)}
    building_control = bc_service.summarize_jobs(
        construction_ids, merged_by_project, calc_ids, scan_by_project
    )

    total_count = sum(b.construction_project_count for b in director_out)
    total_complete = sum(b.calc_package_complete_count for b in director_out)
    totals = OverviewTotals(
        construction_project_count=total_count,
        calc_package_complete_count=total_complete,
        calc_package_completion_pct=(
            round((total_complete / total_count) * 100, 1) if total_count else 0.0
        ),
    )
    return OverviewOut(
        directors=director_out,
        completion_by_director=completion_by_director,
        totals=totals,
        director_analysis=director_analysis,
        qa_stage_distribution=_qa_stage_counts_to_list(agg_qa_counts, stage_order),
        cmap_stage_distribution=_cmap_stage_counts_to_list(agg_cmap_counts),
        analysis_totals=analysis_totals,
        building_control=building_control,
    )


def _qa_stage_counts_to_list(
    counts: Mapping[str, int], stage_order: Mapping[str, int]
) -> list[StageCount]:
    """QA-stage buckets in lifecycle order (Concept → Archive), with the
    "No QA Started" bucket pinned last."""
    return [
        StageCount(stage_name=name, project_count=count)
        for name, count in sorted(
            counts.items(),
            key=lambda kv: (stage_order.get(kv[0], 10_000), kv[0]),
        )
    ]


def _cmap_stage_counts_to_list(counts: Mapping[str, int]) -> list[StageCount]:
    """CMAP-stage buckets by project count (desc), with "Not synced" pinned last.

    The migrated ``cmap_stage`` is free text from a one-off legacy pull, so it has
    a long tail of one-off / mis-entered values (project names, ad-hoc notes).
    Collapse singletons — and anything past the top N — into a single "Other"
    bucket so the distribution stays readable."""
    not_synced = counts.get(NOT_SYNCED, 0)
    real = sorted(
        ((k, v) for k, v in counts.items() if k != NOT_SYNCED),
        key=lambda kv: (-kv[1], kv[0]),
    )

    kept: list[tuple[str, int]] = []
    other = 0
    for name, count in real:
        if count <= 1 or len(kept) >= CMAP_TOP_N:
            other += count
        else:
            kept.append((name, count))

    out = [StageCount(stage_name=name, project_count=count) for name, count in kept]
    if other:
        out.append(StageCount(stage_name=CMAP_OTHER, project_count=other))
    if not_synced:
        out.append(StageCount(stage_name=NOT_SYNCED, project_count=not_synced))
    return out
