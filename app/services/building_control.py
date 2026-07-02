from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.models.building_control import QaBuildingControl
from app.models.user import User
from app.repositories import building_control as bc_repo
from app.repositories import forms as forms_repo
from app.repositories import projects as projects_repo
from app.repositories import responses as responses_repo
from app.schemas.building_control import (
    BuildingControlList,
    BuildingControlOut,
    BuildingControlSummary,
    BuildingControlUpdate,
)
from app.services import construction
from app.services import responses as responses_service

# How the J: scan compares to the canonical form verdict.
MATCH = "match"
SCAN_ONLY = "scan_only"  # scan found a pack but the form isn't "yes"
FORM_ONLY = "form_only"  # form says "yes" but the scan found nothing
NO_SCAN = "no_scan"


def _agreement(form_status: str, scan: QaBuildingControl | None) -> str:
    if scan is None:
        return NO_SCAN
    form_yes = form_status == construction.CALC_YES
    if form_yes == bool(scan.scan_detected):
        return MATCH
    return FORM_ONLY if form_yes else SCAN_ONLY


def _build_out(
    project: Any, form_status: str, scan: QaBuildingControl | None
) -> BuildingControlOut:
    return BuildingControlOut(
        project_id=project.id,
        project_number=project.number,
        project_name=project.name,
        director_name=project.director.display_name if project.director else None,
        manager_name=project.manager.display_name if project.manager else None,
        form_status=form_status,
        present=form_status == construction.CALC_YES,
        scanned=scan is not None,
        scan_detected=bool(scan.scan_detected) if scan else False,
        scan_status=scan.scan_status if scan else None,
        scan_path=scan.scan_path if scan else None,
        scanned_at=scan.scanned_at if scan else None,
        agreement=_agreement(form_status, scan),
    )


def summarize_jobs(
    project_ids: Iterable[uuid.UUID],
    merged_by_project: Mapping[uuid.UUID, Mapping[str, Any]],
    calc_ids: list[str],
    scan_by_project: Mapping[uuid.UUID, QaBuildingControl],
) -> BuildingControlSummary:
    """Pure roll-up shared by the register and the overview KPI."""
    total = present = absent = blank = scanned = detected = mismatch = 0
    for pid in project_ids:
        status = construction.calc_pack_status(merged_by_project.get(pid, {}), calc_ids)
        total += 1
        if status == construction.CALC_YES:
            present += 1
        elif status == construction.CALC_NO:
            absent += 1
        else:
            blank += 1
        scan = scan_by_project.get(pid)
        if scan is not None:
            scanned += 1
            if scan.scan_detected:
                detected += 1
            if (status == construction.CALC_YES) != bool(scan.scan_detected):
                mismatch += 1
    return BuildingControlSummary(
        total=total,
        present=present,
        absent=absent,
        blank=blank,
        scanned=scanned,
        detected=detected,
        mismatch=mismatch,
    )


async def list_status(
    session: AsyncSession,
    director_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    status: str | None = None,
) -> BuildingControlList:
    """The calc-package / Building Control register: every active construction job
    with its canonical form verdict and the advisory J: scan hint. Optional
    ``director``/``project`` narrow the population; ``status`` (yes|no|blank)
    filters the items while the summary stays over the full scoped set."""
    projects = list(await projects_repo.list_active(session))
    if director_id is not None:
        projects = [p for p in projects if p.director_id == director_id]

    all_responses = await responses_repo.list_for_projects(session, [p.id for p in projects])
    construction_ids = await construction.construction_project_ids(
        session, projects, all_responses
    )
    merged = construction.merge_construction_responses(all_responses, construction_ids)
    scan_by_project = {r.project_id: r for r in await bc_repo.list_all(session)}
    calc_ids = settings.calc_pack_ids

    jobs = [p for p in projects if p.id in construction_ids]
    if project_id is not None:
        jobs = [p for p in jobs if p.id == project_id]
    jobs.sort(key=lambda p: p.number)

    items = [
        _build_out(
            p,
            construction.calc_pack_status(merged.get(p.id, {}), calc_ids),
            scan_by_project.get(p.id),
        )
        for p in jobs
    ]
    if status is not None:
        items = [i for i in items if i.form_status == status]

    summary = summarize_jobs([p.id for p in jobs], merged, calc_ids, scan_by_project)
    return BuildingControlList(summary=summary, items=items)


def _structure_has_question(structure: Mapping[str, Any], qid: str) -> bool:
    for section in structure.get("sections", []) or []:
        for question in section.get("questions", []) or []:
            if question.get("id") == qid:
                return True
            subform = question.get("subform") or {}
            for sub_q in subform.get("questions", []) or []:
                if sub_q.get("id") == qid:
                    return True
    return False


async def _resolve_calc_pack_target(session: AsyncSession) -> tuple[uuid.UUID, str]:
    """(stage_id, question_id) the director's calc-pack confirm writes to — the
    active form that actually carries the configured canonical question."""
    qid = settings.calc_pack_primary_question_id
    for form in await forms_repo.list_active(session):
        if _structure_has_question(form.structure, qid):
            return form.stage_id, qid
    raise NotFoundError(f"No active form contains calc-pack question '{qid}'")


async def _build_one(session: AsyncSession, project_id: uuid.UUID) -> BuildingControlOut:
    project = await projects_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError("Project not found")
    responses = await responses_repo.list_for_projects(session, [project_id])
    construction_ids = await construction.construction_project_ids(
        session, [project], responses
    )
    merged = construction.merge_construction_responses(responses, construction_ids)
    scan = await bc_repo.get_by_project(session, project_id)
    form_status = construction.calc_pack_status(
        merged.get(project_id, {}), settings.calc_pack_ids
    )
    return _build_out(project, form_status, scan)


async def set_calc_pack(
    session: AsyncSession,
    project_id: uuid.UUID,
    payload: BuildingControlUpdate,
    user: User,
    building_id: uuid.UUID | None = None,
) -> BuildingControlOut:
    """Director confirm/override: write the canonical calc-package form answer
    (``present`` → "Yes"/"No") via the normal save path, so the QA form and the
    director KPI both reflect it. The J: scan never writes here."""
    if await projects_repo.get_by_id(session, project_id) is None:
        raise NotFoundError("Project not found")

    stage_id, qid = await _resolve_calc_pack_target(session)
    await responses_service.set_answer(
        session,
        project_id=project_id,
        stage_id=stage_id,
        question_id=qid,
        value="Yes" if payload.present else "No",
        user=user,
        building_id=building_id,
    )
    return await _build_one(session, project_id)
