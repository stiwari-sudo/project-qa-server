from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.building_control import QaBuildingControl
from app.models.user import User
from app.repositories import building_control as bc_repo
from app.repositories import projects as projects_repo
from app.schemas.building_control import (
    BuildingControlList,
    BuildingControlOut,
    BuildingControlSummary,
    BuildingControlUpdate,
)

# Effective-status vocabulary (manual override else scan hint).
FOUND = "found"
NOT_FOUND = "not_found"
UNKNOWN = "unknown"

# Director override accepts only the resolved verdicts (or None to defer to scan).
_MANUAL_VALUES = (FOUND, NOT_FOUND)


def effective_status(row: QaBuildingControl) -> str:
    """A director's confirm/override wins; otherwise the scan hint. ``unknown``
    when neither a decision nor a usable scan exists — the scan errored, found no
    "4 Calculations" folder, or never ran."""
    if row.manual_status == FOUND:
        return FOUND
    if row.manual_status == NOT_FOUND:
        return NOT_FOUND
    if row.scan_detected:
        return FOUND
    if row.scan_status == "not-found":
        return NOT_FOUND
    return UNKNOWN


def _to_out(row: QaBuildingControl) -> BuildingControlOut:
    project = row.project
    director = project.director if project else None
    manager = project.manager if project else None
    return BuildingControlOut(
        project_id=row.project_id,
        project_number=project.number if project else "",
        project_name=project.name if project else "",
        director_name=director.display_name if director else None,
        manager_name=manager.display_name if manager else None,
        scan_detected=row.scan_detected,
        scan_status=row.scan_status,
        scan_detail=row.scan_detail,
        scan_path=row.scan_path,
        scanned_at=row.scanned_at,
        manual_status=row.manual_status,
        effective_status=effective_status(row),
        confirmed_by_name=row.confirmed_by.display_name if row.confirmed_by else None,
        notes=row.notes,
        updated_at=row.updated_at,
    )


def summarize(rows: Iterable[QaBuildingControl]) -> BuildingControlSummary:
    found = not_found = unknown = confirmed = 0
    for row in rows:
        if row.manual_status is not None:
            confirmed += 1
        status = effective_status(row)
        if status == FOUND:
            found += 1
        elif status == NOT_FOUND:
            not_found += 1
        else:
            unknown += 1
    total = found + not_found + unknown
    return BuildingControlSummary(
        total=total,
        found=found,
        not_found=not_found,
        unknown=unknown,
        confirmed=confirmed,
        found_pct=round(found / total * 100, 1) if total else 0.0,
    )


async def list_status(
    session: AsyncSession,
    director_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    status: str | None = None,
) -> BuildingControlList:
    """The Building Control register: every scanned construction job with its
    effective status, plus a roll-up summary. Archived projects are excluded (the
    register tracks live construction oversight). Optional ``director``/``project``
    narrow the population; ``status`` filters the returned items to one effective
    status (e.g. the actionable ``unknown``/``not_found``) while the summary stays
    over the full director/project-scoped population so its percentages stay
    meaningful."""
    rows = [r for r in await bc_repo.list_all(session) if r.project and not r.project.archived]
    if director_id is not None:
        rows = [r for r in rows if r.project.director_id == director_id]
    if project_id is not None:
        rows = [r for r in rows if r.project_id == project_id]
    rows.sort(key=lambda r: r.project.number)

    items = rows if status is None else [r for r in rows if effective_status(r) == status]
    return BuildingControlList(
        summary=summarize(rows),
        items=[_to_out(r) for r in items],
    )


async def set_manual(
    session: AsyncSession,
    project_id: uuid.UUID,
    payload: BuildingControlUpdate,
    user: User,
) -> BuildingControlOut:
    """Record (or clear) a director's confirm/override for a job's Building
    Control status. A partial update (only the provided fields change); setting
    ``manual_status`` stamps/clears the confirmer, and clearing it
    (``manual_status=None``) makes the effective status fall back to the scan
    hint."""
    data = payload.model_dump(exclude_unset=True)
    manual_given = "manual_status" in data
    manual_status = data.get("manual_status")
    if manual_given and manual_status is not None and manual_status not in _MANUAL_VALUES:
        raise ValidationAppError(
            f"manual_status must be one of {', '.join(_MANUAL_VALUES)} or null"
        )
    if await projects_repo.get_by_id(session, project_id) is None:
        raise NotFoundError("Project not found")

    row = await bc_repo.get_or_create(session, project_id)
    if manual_given:
        row.manual_status = manual_status
        row.confirmed_by_id = user.id if manual_status is not None else None
    if "notes" in data:
        row.notes = data["notes"]
    await session.flush()
    return _to_out(await bc_repo.reload(session, project_id))
