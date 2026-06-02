from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_by_azure_oid(session: AsyncSession, azure_oid: str) -> User | None:
    result = await session.execute(select(User).where(User.azure_oid == azure_oid))
    return result.scalar_one_or_none()


async def list_all(session: AsyncSession) -> Sequence[User]:
    result = await session.execute(select(User).order_by(User.display_name))
    return result.scalars().all()


async def create(
    session: AsyncSession,
    *,
    email: str,
    display_name: str,
    roles: list[str] | None = None,
    azure_oid: str | None = None,
) -> User:
    user = User(
        email=email,
        display_name=display_name,
        roles=roles or [],
        azure_oid=azure_oid,
    )
    session.add(user)
    await session.flush()
    return user
