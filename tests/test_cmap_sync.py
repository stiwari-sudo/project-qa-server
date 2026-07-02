"""CMAP sync — field-mapping unit tests (no network/DB) plus one end-to-end
upsert against a throwaway database using a fake CMap client.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings, settings
from app.models.base import Base
from app.repositories import projects as projects_repo
from app.repositories import users as users_repo
from app.services.cmap_client import _extract_items
from app.services.cmap_sync import (
    map_project,
    map_user,
    resolve_role,
    run_sync,
)

# --------------------------------------------------------------------------- #
# Pure mapping (no I/O)
# --------------------------------------------------------------------------- #


def test_map_user_pascal_case() -> None:
    mu = map_user(
        {
            "Id": "u1",
            "EmailAddress": "Jane.Doe@HTS.uk.com",
            "FirstName": "Jane",
            "LastName": "Doe",
            "IsEnabled": True,
            "SecurityGroup": "Director",
        }
    )
    assert mu.cmap_id == "u1"
    assert mu.email == "jane.doe@hts.uk.com"  # normalised
    assert mu.name == "Jane Doe"
    assert mu.is_active is True
    assert mu.cmap_role == "Director"


def test_map_user_disabled_leaver_is_inactive() -> None:
    mu = map_user({"id": "u2", "email": "x@hts.uk.com", "fullName": "X", "isDisabled": True})
    assert mu.is_active is False


def test_map_project_with_nested_director() -> None:
    mp = map_project(
        {
            "id": "p1",
            "projectCode": "2001",
            "name": "Wells House",
            "status": "Construction",
            "projectDirector": {"id": "u1", "name": "Jane"},
            "projectManager": "mgr@hts.uk.com",
        }
    )
    assert mp.cmap_id == "p1"
    assert mp.number == "2001"
    assert mp.name == "Wells House"
    assert mp.stage == "Construction"
    assert mp.director_ref == "u1"  # unwrapped from the nested person object
    assert mp.manager_ref == "mgr@hts.uk.com"


def test_resolve_role_maps_known_and_drops_unknown() -> None:
    role_map = {"director": "director", "associate": "associate_director"}
    assert resolve_role("Director", role_map) == ["director"]
    assert resolve_role("Associate", role_map) == ["associate_director"]
    assert resolve_role("Draughtsman", role_map) == []  # unmapped → fail closed
    assert resolve_role(None, role_map) == []


def test_extract_items_handles_array_and_envelopes() -> None:
    assert _extract_items([{"a": 1}]) == [{"a": 1}]
    assert _extract_items({"items": [{"a": 1}]}) == [{"a": 1}]
    assert _extract_items({"value": [{"b": 2}]}) == [{"b": 2}]
    assert _extract_items({"totalCount": 0, "items": []}) == []
    assert _extract_items({"nope": 1}) == []


def test_role_map_parsing() -> None:
    s = Settings(
        _env_file=None,
        cmap_role_map="Director=director, Associate Director=associate_director",
    )
    assert s.cmap_role_map_parsed == {
        "director": "director",
        "associate director": "associate_director",
    }
    assert Settings(_env_file=None).cmap_role_map_parsed == {}


# --------------------------------------------------------------------------- #
# End-to-end upsert (throwaway PG; skips if the cluster is down)
# --------------------------------------------------------------------------- #

_HOST = "127.0.0.1:5544"
_ADMIN_URL = f"postgresql+asyncpg://qa@{_HOST}/postgres"
_TEST_DB = "projectqa_cmap_test"
_TEST_URL = f"postgresql+asyncpg://qa@{_HOST}/{_TEST_DB}"


class FakeCmapClient:
    def __init__(self, users: list[dict[str, Any]], projects: list[dict[str, Any]]):
        self._data = {"/v1/Users": users, "/v1/Projects": projects}

    async def get_all(self, path: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        rows = self._data.get(path, [])
        return rows[:limit] if limit else rows


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
        pytest.skip(f"no Postgres reachable on {_HOST} for the CMAP sync test DB")
    engine = create_async_engine(_TEST_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_sync_upserts_users_and_projects_with_roles_and_director(
    session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "cmap_role_map", "Director=director")
    client = FakeCmapClient(
        users=[
            {"id": "u1", "email": "Dir@hts.uk.com", "fullName": "Dir Person",
             "isActive": True, "securityGroup": "Director"},
            {"id": "u2", "email": "eng@hts.uk.com", "firstName": "Eng",
             "lastName": "Ineer", "securityGroup": "Draughtsman"},
        ],
        projects=[
            {"id": "p1", "code": "2001", "name": "Job A", "stage": "Construction",
             "projectDirector": {"id": "u1"}},
        ],
    )

    async with session_factory() as s:
        summary = await run_sync(s, client=client)  # type: ignore[arg-type]

    assert summary.users_created == 2
    assert summary.projects_created == 1

    async with session_factory() as s:
        director = await users_repo.get_by_email(s, "dir@hts.uk.com")
        engineer = await users_repo.get_by_email(s, "eng@hts.uk.com")
        assert director is not None and director.roles == ["director"]
        # Unmapped CMap role → no QA role (fail closed).
        assert engineer is not None and engineer.roles == []

        project = await projects_repo.get_by_cmap_ref(s, "p1")
        assert project is not None
        assert project.number == "2001"
        assert project.cmap_stage == "Construction"
        assert project.director_id == director.id  # linked via the CMap id map


async def test_sync_dry_run_writes_nothing(
    session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "cmap_role_map", "Director=director")
    client = FakeCmapClient(
        users=[
            {"id": "u1", "email": "dir@hts.uk.com", "fullName": "Dir",
             "securityGroup": "Director"}
        ],
        projects=[{"id": "p1", "code": "2001", "name": "Job A", "stage": "Construction"}],
    )
    async with session_factory() as s:
        summary = await run_sync(s, client=client, dry_run=True)  # type: ignore[arg-type]
        assert summary.dry_run is True
        assert summary.sample_user_keys  # keys surfaced for mapping confirmation

    async with session_factory() as s:
        assert await users_repo.get_by_email(s, "dir@hts.uk.com") is None
        assert await projects_repo.get_by_cmap_ref(s, "p1") is None
