"""MSAL is login-only: the Azure provider establishes identity but never
sources roles from the token — roles are owned by the CMAP sync.

Runs against a throwaway database on the local dev cluster; skips cleanly when
no Postgres is reachable on 127.0.0.1:5544 (the models use PG-dialect types).
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.azure import AzureJwksProvider
from app.models.base import Base
from app.repositories import users as users_repo

_HOST = "127.0.0.1:5544"
_ADMIN_URL = f"postgresql+asyncpg://qa@{_HOST}/postgres"
_TEST_DB = "projectqa_azure_test"
_TEST_URL = f"postgresql+asyncpg://qa@{_HOST}/{_TEST_DB}"


class _FakeHeaders:
    def get(self, key: str, default: str = "") -> str:
        return "Bearer test-token" if key == "Authorization" else default


class _FakeRequest:
    headers = _FakeHeaders()


def _provider_returning(claims: dict[str, Any]) -> AzureJwksProvider:
    provider = AzureJwksProvider()
    provider._tenant = "test-tenant"

    async def _fake_verify(_token: str) -> dict[str, Any]:
        return claims

    provider._verify = _fake_verify  # type: ignore[method-assign]
    return provider


async def _prepare_database() -> bool:
    try:
        engine = create_async_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as conn:
                await conn.execute(text(f"DROP DATABASE IF EXISTS {_TEST_DB} WITH (FORCE)"))
                await conn.execute(text(f"CREATE DATABASE {_TEST_DB}"))
        finally:
            await engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture
async def session_factory() -> Any:
    if not await _prepare_database():
        pytest.skip(f"no Postgres reachable on {_HOST} for the azure identity test DB")
    engine = create_async_engine(_TEST_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_first_login_provisions_role_less_ignoring_token_roles(
    session_factory: Any,
) -> None:
    provider = _provider_returning(
        {
            "oid": "azure-oid-1",
            "preferred_username": "New.Person@hts.uk.com",
            "name": "New Person",
            # A token that TRIES to grant elevated access — must be ignored.
            "roles": ["admin", "director"],
            "groups": ["11111111-2222-3333-4444-555555555555"],
        }
    )
    async with session_factory() as s:
        user = await provider.resolve_user(s, _FakeRequest())
        await s.commit()
        assert user.email == "new.person@hts.uk.com"  # normalised
        assert user.azure_oid == "azure-oid-1"
        assert user.roles == []  # roles come from CMAP, never the token


async def test_existing_user_roles_are_never_overwritten_by_token(
    session_factory: Any,
) -> None:
    async with session_factory() as s:
        # A user as the CMAP sync would create it: email-keyed, real role, no oid.
        await users_repo.create(
            s,
            email="dir@hts.uk.com",
            display_name="Old Name",
            roles=["director"],
        )
        await s.commit()

    provider = _provider_returning(
        {
            "oid": "azure-oid-2",
            "preferred_username": "dir@hts.uk.com",
            "name": "Dir Refreshed",
            "roles": ["engineer"],  # token trying to DEMOTE — must be ignored
        }
    )
    async with session_factory() as s:
        user = await provider.resolve_user(s, _FakeRequest())
        await s.commit()
        assert user.roles == ["director"]  # CMAP-owned, untouched
        assert user.azure_oid == "azure-oid-2"  # identity linked on first login
        assert user.display_name == "Dir Refreshed"  # identity fields refresh
