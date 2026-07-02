from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import RequireViewAll
from app.core.db import get_session
from app.schemas.overview import OverviewOut
from app.services import overview as overview_service

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("", response_model=OverviewOut)
async def get_overview(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: RequireViewAll,
    director: uuid.UUID | None = None,
) -> OverviewOut:
    return await overview_service.build_overview(session, director_id=director)
