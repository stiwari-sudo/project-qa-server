from __future__ import annotations

from collections.abc import Callable, Coroutine
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.azure import AzureJwksProvider
from app.auth.dev import DevStubProvider
from app.auth.provider import AuthProvider
from app.core.config import settings
from app.core.db import get_session
from app.core.exceptions import PermissionDeniedError
from app.models.user import User


@lru_cache
def get_auth_provider() -> AuthProvider:
    if settings.auth_provider == "azure":
        return AzureJwksProvider()
    return DevStubProvider()


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    provider = get_auth_provider()
    return await provider.resolve_user(session, request)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(
    *roles: str,
) -> Callable[[User], Coroutine[Any, Any, User]]:
    """Dependency factory: require the user to hold at least one of ``roles``."""
    wanted = set(roles)

    async def _checker(user: CurrentUser) -> User:
        if wanted and not wanted.intersection(user.roles):
            raise PermissionDeniedError(
                f"Requires one of roles: {', '.join(sorted(wanted))}"
            )
        return user

    return _checker
