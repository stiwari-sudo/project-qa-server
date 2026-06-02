from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.hrb import QaHighRiskBuilding
from app.models.user import User
from app.repositories import hrb as hrb_repo
from app.repositories import projects as projects_repo
from app.schemas.hrb import HrbCreate, HrbOut, HrbUpdate
from app.services.mappers import hrb_to_out


async def list_hrb(
    session: AsyncSession,
    *,
    project_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    is_high_risk: bool | None = None,
) -> list[HrbOut]:
    rows = await hrb_repo.list_filtered(
        session,
        project_id=project_id,
        stage_id=stage_id,
        is_high_risk=is_high_risk,
    )
    return [hrb_to_out(r) for r in rows]


async def get_hrb(session: AsyncSession, hrb_id: uuid.UUID) -> HrbOut:
    row = await hrb_repo.get_by_id(session, hrb_id)
    if row is None:
        raise NotFoundError("HRB record not found")
    return hrb_to_out(row)


async def upsert_hrb(
    session: AsyncSession, payload: HrbCreate, user: User
) -> HrbOut:
    """Manual create/update honouring the (project, stage) uniqueness."""
    project = await projects_repo.get_by_id(session, payload.project_id)
    if project is None:
        raise NotFoundError("Project not found")

    existing = await hrb_repo.get_by_project_stage(
        session, payload.project_id, payload.stage_id
    )
    if existing is not None:
        existing.is_high_risk = payload.is_high_risk
        existing.notes = payload.notes
        existing.checked_by_id = user.id
        await session.flush()
        reloaded = await hrb_repo.get_by_id(session, existing.id)
        assert reloaded is not None
        return hrb_to_out(reloaded)

    created = await hrb_repo.add(
        session,
        QaHighRiskBuilding(
            project_id=payload.project_id,
            stage_id=payload.stage_id,
            is_high_risk=payload.is_high_risk,
            notes=payload.notes,
            checked_by_id=user.id,
        ),
    )
    return hrb_to_out(created)


async def update_hrb(
    session: AsyncSession, hrb_id: uuid.UUID, payload: HrbUpdate, user: User
) -> HrbOut:
    row = await hrb_repo.get_by_id(session, hrb_id)
    if row is None:
        raise NotFoundError("HRB record not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    row.checked_by_id = user.id
    await session.flush()

    reloaded = await hrb_repo.get_by_id(session, hrb_id)
    assert reloaded is not None
    return hrb_to_out(reloaded)


async def delete_hrb(session: AsyncSession, hrb_id: uuid.UUID) -> None:
    row = await hrb_repo.get_by_id(session, hrb_id)
    if row is None:
        raise NotFoundError("HRB record not found")
    await hrb_repo.delete(session, row)
