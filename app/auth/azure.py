from __future__ import annotations

from typing import Any, cast

import httpx
from fastapi import Request
from jose import jwt
from jose.exceptions import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.provider import AuthProvider, display_name_from_email
from app.core.config import settings
from app.core.exceptions import AuthenticationError
from app.core.logging import get_logger
from app.models.user import User
from app.repositories import users as users_repo

logger = get_logger(__name__)

_ROLE_CLAIMS = ("roles", "groups")


class AzureJwksProvider(AuthProvider):
    """Verifies an Azure AD bearer JWT (RS256) against the tenant JWKS.

    Phase 4 slot. Same contract as the dev stub: it maps ``oid/upn/name/roles``
    claims and JIT-provisions a User. Selected when ``AUTH_PROVIDER=azure``.
    """

    def __init__(self) -> None:
        self._tenant = settings.azure_tenant_id
        self._audience = settings.azure_audience or settings.azure_client_id
        self._jwks_cache: dict[str, Any] | None = None

    @property
    def _jwks_url(self) -> str:
        return f"https://login.microsoftonline.com/{self._tenant}/discovery/v2.0/keys"

    @property
    def _issuer(self) -> str:
        return f"https://login.microsoftonline.com/{self._tenant}/v2.0"

    async def _jwks(self) -> dict[str, Any]:
        if self._jwks_cache is None:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self._jwks_url)
                resp.raise_for_status()
                self._jwks_cache = resp.json()
        return self._jwks_cache

    async def resolve_user(self, session: AsyncSession, request: Request) -> User:
        if not self._tenant:
            raise AuthenticationError("Azure auth is not configured")

        token = _bearer_token(request)
        claims = await self._verify(token)

        azure_oid = str(claims.get("oid") or "") or None
        email = str(
            claims.get("preferred_username")
            or claims.get("upn")
            or claims.get("email")
            or ""
        ).strip().lower()
        if not email:
            raise AuthenticationError("Token has no email/upn claim")

        name = str(claims.get("name") or "") or display_name_from_email(email)
        roles = _extract_roles(claims)

        user: User | None = None
        if azure_oid:
            user = await users_repo.get_by_azure_oid(session, azure_oid)
        if user is None:
            user = await users_repo.get_by_email(session, email)

        if user is None:
            user = await users_repo.create(
                session,
                email=email,
                display_name=name,
                roles=roles,
                azure_oid=azure_oid,
            )
        else:
            # Keep the local mirror fresh on each sign-in.
            user.display_name = name
            if roles:
                user.roles = roles
            if azure_oid and not user.azure_oid:
                user.azure_oid = azure_oid

        if not user.is_active:
            raise AuthenticationError("User is inactive")
        return user

    async def _verify(self, token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except JWTError as exc:
            raise AuthenticationError("Malformed token") from exc

        kid = header.get("kid")
        jwks = await self._jwks()
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if key is None:
            # Key may have rotated; refresh once.
            self._jwks_cache = None
            jwks = await self._jwks()
            key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if key is None:
            raise AuthenticationError("Signing key not found")

        try:
            return cast(
                dict[str, Any],
                jwt.decode(
                    token,
                    key,
                    algorithms=["RS256"],
                    audience=self._audience,
                    issuer=self._issuer,
                ),
            )
        except JWTError as exc:
            raise AuthenticationError("Token verification failed") from exc


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationError("Missing bearer token")
    return token.strip()


def _extract_roles(claims: dict[str, Any]) -> list[str]:
    for claim in _ROLE_CLAIMS:
        value = claims.get(claim)
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, str) and value:
            return [value]
    return []
