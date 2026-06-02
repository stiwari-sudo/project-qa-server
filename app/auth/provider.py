from __future__ import annotations

from abc import ABC, abstractmethod

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class AuthProvider(ABC):
    """Resolves the authenticated User for a request.

    Concrete providers (dev stub now, Azure JWKS later) implement the same
    contract so the rest of the app depends only on this interface.
    """

    @abstractmethod
    async def resolve_user(self, session: AsyncSession, request: Request) -> User:
        """Return the User making this request, or raise AuthenticationError."""
        raise NotImplementedError


def display_name_from_email(email: str) -> str:
    local = email.split("@", 1)[0]
    parts = [p for p in local.replace(".", " ").replace("_", " ").split() if p]
    return " ".join(p.capitalize() for p in parts) or email
