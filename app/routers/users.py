from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.core.db import get_session
from app.repositories import users as users_repo
from app.schemas.user import UserOut

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserOut)
async def get_me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/users", response_model=list[UserOut])
async def list_users(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: CurrentUser,
) -> list[UserOut]:
    rows = await users_repo.list_all(session)
    return [UserOut.model_validate(u) for u in rows]
