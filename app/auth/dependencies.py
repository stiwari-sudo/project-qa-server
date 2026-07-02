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
    if settings.auth_provider == "dev":
        return DevStubProvider()
    # Settings validation makes this unreachable — but never fall back to the
    # header-trusting dev stub on an unrecognised value.
    raise RuntimeError(f"Unknown auth_provider {settings.auth_provider!r}")


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    provider = get_auth_provider()
    return await provider.resolve_user(session, request)


CurrentUser = Annotated[User, Depends(get_current_user)]


# Ordered low→high authority. Used for display/sorting only — the visibility
# rule below does NOT depend on the ordering. Roles are free strings on the
# user (sourced from SharePoint/Azure later), so unknown roles are tolerated.
ROLE_HIERARCHY: tuple[str, ...] = (
    "engineer",
    "associate",
    "senior_associate",
    "associate_director",
    "manager",
    "director",
    "founding_director",
    "admin",
)


def can_view_all_projects(user: User) -> bool:
    """Whether the user sees every project (vs. only the ones assigned to them).

    Rule: a user is "view-all" if they hold ANY role other than ``engineer``.
    A pure engineer (``["engineer"]`` or no roles) is restricted to their own
    assigned projects. Robust to future role strings — anything non-engineer
    grants the all-projects view.
    """
    return any(role != "engineer" for role in user.roles)


async def require_view_all(user: CurrentUser) -> User:
    """Dependency: firm-wide roll-up surfaces (the director overview) are for
    view-all roles only — own-only engineers get 403. Mirrors the web
    RouteGuard's VIEW_ALL_PREFIXES policy on the server."""
    if not can_view_all_projects(user):
        raise PermissionDeniedError("Requires all-projects visibility")
    return user


RequireViewAll = Annotated[User, Depends(require_view_all)]


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
