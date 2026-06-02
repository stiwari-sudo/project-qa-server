from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.repositories import stages as stages_repo
from app.schemas.stage import StageOut

router = APIRouter(prefix="/stages", tags=["stages"])


@router.get("", response_model=list[StageOut])
async def list_stages(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[StageOut]:
    rows = await stages_repo.list_ordered(session)
    return [StageOut.model_validate(s) for s in rows]
