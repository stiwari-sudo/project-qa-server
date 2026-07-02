from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.hrb import QaHighRiskBuilding
from app.models.user import User
from app.repositories import hrb as hrb_repo
from app.repositories import responses as responses_repo
from app.schemas.hrb import HrbCreate, HrbOut, HrbUpdate
from app.services import buildings as buildings_service
from app.services import project_members as members_service
from app.services.mappers import hrb_to_out


async def list_hrb(
    session: AsyncSession,
    *,
    project_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    is_high_risk: bool | None = None,
    visible_project_ids: set[uuid.UUID] | None = None,
) -> list[HrbOut]:
    rows = await hrb_repo.list_filtered(
        session,
        project_id=project_id,
        stage_id=stage_id,
        is_high_risk=is_high_risk,
        visible_project_ids=visible_project_ids,
    )
    # Group each project's stages together in QA lifecycle order.
    rows = sorted(
        rows,
        key=lambda r: (r.project.number, r.stage.order if r.stage else -1),
    )
    # Join each (project, stage) to that stage's QA-form completion % — the same
    # number the project detail view's completion ring shows for the stage.
    project_ids = list({r.project_id for r in rows})
    responses = await responses_repo.list_for_projects(session, project_ids)
    # Keyed by (building, stage); HRB rows may have a null stage, so the key type
    # widens to match the lookup below (a null stage simply finds no completion).
    completion_by_stage: dict[tuple[uuid.UUID, uuid.UUID | None], float] = {
        (resp.building_id, resp.stage_id): resp.completion_percentage
        for resp in responses
    }
    return [
        hrb_to_out(r, completion_by_stage.get((r.building_id, r.stage_id)))
        for r in rows
    ]


async def get_hrb(session: AsyncSession, hrb_id: uuid.UUID) -> HrbOut:
    row = await hrb_repo.get_by_id(session, hrb_id)
    if row is None:
        raise NotFoundError("HRB record not found")
    return hrb_to_out(row)


async def upsert_hrb(
    session: AsyncSession, payload: HrbCreate, user: User
) -> HrbOut:
    """Manual create/update honouring the (building, stage) uniqueness. The
    building defaults to the project's primary one when the caller omits it."""
    await members_service.assert_can_view_project(session, user, payload.project_id)
    building = await buildings_service.resolve_building(
        session, payload.project_id, payload.building_id
    )

    existing = await hrb_repo.get_by_building_stage(
        session, building.id, payload.stage_id
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
            project_id=building.project_id,
            building_id=building.id,
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
    await members_service.assert_can_view_project(session, user, row.project_id)

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    row.checked_by_id = user.id
    await session.flush()

    reloaded = await hrb_repo.get_by_id(session, hrb_id)
    assert reloaded is not None
    return hrb_to_out(reloaded)


async def delete_hrb(session: AsyncSession, hrb_id: uuid.UUID, user: User) -> None:
    row = await hrb_repo.get_by_id(session, hrb_id)
    if row is None:
        raise NotFoundError("HRB record not found")
    await members_service.assert_can_view_project(session, user, row.project_id)
    await hrb_repo.delete(session, row)
