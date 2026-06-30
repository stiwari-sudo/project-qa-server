from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.building_control import QaBuildingControl
from app.models.project import Project

_LOAD = (
    selectinload(QaBuildingControl.confirmed_by),
    selectinload(QaBuildingControl.project).selectinload(Project.director),
    selectinload(QaBuildingControl.project).selectinload(Project.manager),
)


async def get_by_project(
    session: AsyncSession, project_id: uuid.UUID
) -> QaBuildingControl | None:
    result = await session.execute(
        select(QaBuildingControl)
        .where(QaBuildingControl.project_id == project_id)
        .options(*_LOAD)
    )
    return result.scalar_one_or_none()


async def list_all(session: AsyncSession) -> Sequence[QaBuildingControl]:
    result = await session.execute(select(QaBuildingControl).options(*_LOAD))
    return result.scalars().all()


async def upsert_scan(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    scan_detected: bool,
    scan_status: str,
    scan_detail: str | None,
    scan_path: str | None,
    scanned_at: datetime,
) -> QaBuildingControl:
    """Write the latest scan result, leaving any manual override untouched."""
    row = await get_by_project(session, project_id)
    if row is None:
        row = QaBuildingControl(project_id=project_id)
        session.add(row)
    row.scan_detected = scan_detected
    row.scan_status = scan_status
    row.scan_detail = scan_detail
    row.scan_path = scan_path
    row.scanned_at = scanned_at
    await session.flush()
    return row


async def get_or_create(
    session: AsyncSession, project_id: uuid.UUID
) -> QaBuildingControl:
    """Return the project's row, creating a bare one if the job was never scanned
    (a director can record a decision regardless of scan coverage)."""
    row = await get_by_project(session, project_id)
    if row is None:
        row = QaBuildingControl(project_id=project_id)
        session.add(row)
        await session.flush()
    return row


async def reload(session: AsyncSession, project_id: uuid.UUID) -> QaBuildingControl:
    """Re-read with ``populate_existing`` so the eager-loaded relationships
    (``project``/``confirmed_by``) reflect any just-written FK changes — a plain
    re-query returns the identity-mapped row with its stale relationship state."""
    result = await session.execute(
        select(QaBuildingControl)
        .where(QaBuildingControl.project_id == project_id)
        .options(*_LOAD)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()
