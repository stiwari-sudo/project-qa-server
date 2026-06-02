from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.provider import AuthProvider, display_name_from_email
from app.core.config import settings
from app.core.exceptions import AuthenticationError
from app.models.user import User
from app.repositories import users as users_repo

DEV_USER_HEADER = "X-Dev-User-Email"


class DevStubProvider(AuthProvider):
    """Resolves a seeded user with no Azure credentials.

    The user is chosen by the ``X-Dev-User-Email`` header, falling back to
    ``settings.dev_user_email``. If the user does not exist yet it is created
    on the fly so the stack works before seeds run.
    """

    async def resolve_user(self, session: AsyncSession, request: Request) -> User:
        email = (
            request.headers.get(DEV_USER_HEADER) or settings.dev_user_email
        ).strip().lower()

        user = await users_repo.get_by_email(session, email)
        if user is None:
            user = await users_repo.create(
                session,
                email=email,
                display_name=display_name_from_email(email),
                roles=["engineer", "director"],
            )
        if not user.is_active:
            raise AuthenticationError("User is inactive")
        return user
