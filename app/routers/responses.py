from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.core.db import get_session
from app.schemas.response import BulkSaveIn, ResponseOut
from app.services import responses as responses_service

router = APIRouter(prefix="/projects", tags=["responses"])


@router.get(
    "/{project_id}/stages/{stage_id}/responses",
    response_model=ResponseOut,
)
async def get_stage_responses(
    project_id: uuid.UUID,
    stage_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: CurrentUser,
) -> ResponseOut:
    """Return the response set for a project+stage, creating an empty one if absent."""
    return await responses_service.get_or_create(session, project_id, stage_id)


@router.post(
    "/{project_id}/stages/{stage_id}/responses/bulk",
    response_model=ResponseOut,
)
async def bulk_save_responses(
    project_id: uuid.UUID,
    stage_id: uuid.UUID,
    payload: BulkSaveIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: CurrentUser,
) -> ResponseOut:
    return await responses_service.bulk_save(
        session,
        project_id=project_id,
        stage_id=stage_id,
        payload=payload,
        user=user,
    )


@router.get("/{project_id}/responses", response_model=list[ResponseOut])
async def list_project_responses(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: CurrentUser,
) -> list[ResponseOut]:
    return await responses_service.list_for_project(session, project_id)
