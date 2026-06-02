from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, require_roles
from app.core.db import get_session
from app.schemas.form import FormCreate, FormListItem, FormOut
from app.services import forms as forms_service

router = APIRouter(prefix="/forms", tags=["forms"])


@router.get("", response_model=list[FormListItem])
async def list_forms(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: CurrentUser,
) -> list[FormListItem]:
    return await forms_service.list_active(session)


@router.get("/by-stage/{stage_id}", response_model=FormOut)
async def get_form_by_stage(
    stage_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: CurrentUser,
) -> FormOut:
    return await forms_service.get_active_by_stage(session, stage_id)


@router.post(
    "",
    response_model=FormOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin"))],
)
async def create_form(
    payload: FormCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FormOut:
    return await forms_service.create_form(session, payload)
