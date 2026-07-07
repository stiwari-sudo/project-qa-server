"""Object-level authorization (BOLA) coverage for the QA surfaces.

Own-only engineers must not read or mutate other projects' event logs, HRB
determinations, or buildings, and the firm-wide overview is view-all only.

These tests run the real HTTP stack against a THROWAWAY database
(projectqa_authz_test) on the local dev cluster; they skip cleanly when no
Postgres is reachable on 127.0.0.1:5544 (the models use PG-dialect types, so
SQLite is not an option).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import Depends, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.dependencies import get_current_user
from app.core.db import get_session
from app.main import app
from app.models.base import Base
from app.models.building import Building
from app.models.event_log import Discipline, QaEventLog
from app.models.hrb import QaHighRiskBuilding
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.repositories import users as users_repo

_HOST = "127.0.0.1:5544"
_ADMIN_URL = f"postgresql+asyncpg://qa@{_HOST}/postgres"
_TEST_DB = "projectqa_authz_test"
_TEST_URL = f"postgresql+asyncpg://qa@{_HOST}/{_TEST_DB}"

ENG = {"X-Test-User": "eng@test.local"}
DIR = {"X-Test-User": "dir@test.local"}


def _prepare_database() -> bool:
    async def _prepare() -> None:
        engine = create_async_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as conn:
                await conn.execute(
                    text(f"DROP DATABASE IF EXISTS {_TEST_DB} WITH (FORCE)")
                )
                await conn.execute(text(f"CREATE DATABASE {_TEST_DB}"))
        finally:
            await engine.dispose()

    try:
        asyncio.run(_prepare())
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def _database() -> None:
    if not _prepare_database():
        pytest.skip(f"no Postgres reachable on {_HOST} for the authz test DB")


@dataclass
class Env:
    client: AsyncClient
    p1: str  # project the engineer is a member of
    p2: str  # foreign project
    e2: str  # event log on the foreign project
    h2: str  # HRB row on the foreign project


@pytest.fixture
async def env(_database: None) -> Any:
    engine = create_async_engine(_TEST_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as s:
        eng = User(email="eng@test.local", display_name="Own-only Engineer", roles=["engineer"])
        boss = User(email="dir@test.local", display_name="Director", roles=["director"])
        s.add_all([eng, boss])
        await s.flush()
        p1 = Project(number="1001", name="Own project")
        p2 = Project(number="1002", name="Foreign project")
        s.add_all([p1, p2])
        await s.flush()
        b1 = Building(project_id=p1.id, name="Main building", order=0)
        b2 = Building(project_id=p2.id, name="Main building", order=0)
        s.add_all([b1, b2])
        await s.flush()
        s.add(ProjectMember(project_id=p1.id, user_id=eng.id))
        e1 = QaEventLog(
            project_id=p1.id,
            description="own event",
            category_of_impact="Cost",
            discipline=Discipline.STRUCTURES,
        )
        e2 = QaEventLog(
            project_id=p2.id,
            description="foreign event",
            category_of_impact="Cost",
            discipline=Discipline.STRUCTURES,
        )
        h1 = QaHighRiskBuilding(
            project_id=p1.id, building_id=b1.id, stage_id=None, is_high_risk=True
        )
        h2 = QaHighRiskBuilding(
            project_id=p2.id, building_id=b2.id, stage_id=None, is_high_risk=False
        )
        s.add_all([e1, e2, h1, h2])
        await s.commit()
        ids = Env(
            client=None,  # type: ignore[arg-type]
            p1=str(p1.id),
            p2=str(p2.id),
            e2=str(e2.id),
            h2=str(h2.id),
        )

    async def override_session() -> Any:
        async with session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    async def override_user(
        request: Request,
        session: AsyncSession = Depends(get_session),  # noqa: B008
    ) -> User:
        email = request.headers.get("X-Test-User", "")
        user = await users_repo.get_by_email(session, email)
        assert user is not None, f"unknown test user {email!r}"
        return user

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = override_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ids.client = client
        yield ids
    app.dependency_overrides.clear()
    await engine.dispose()


async def test_event_log_lists_are_scoped_to_visible_projects(env: Env) -> None:
    r = await env.client.get("/api/v1/event-logs", headers=ENG)
    assert r.status_code == 200
    assert [e["description"] for e in r.json()] == ["own event"]

    r = await env.client.get("/api/v1/event-logs", headers=DIR)
    assert len(r.json()) == 2

    r = await env.client.get(f"/api/v1/event-logs?project={env.p2}", headers=ENG)
    assert r.status_code == 403
    r = await env.client.get(f"/api/v1/event-logs?project={env.p2}", headers=DIR)
    assert r.status_code == 200

    r = await env.client.get("/api/v1/event-logs/analysis", headers=ENG)
    assert r.json()["total"] == 1

    r = await env.client.get("/api/v1/event-logs/export", headers=ENG)
    assert "own event" in r.text and "foreign event" not in r.text


async def test_event_log_writes_are_guarded(env: Env) -> None:
    payload = {
        "project_id": env.p2,
        "description": "sneaky",
        "category_of_impact": "Cost",
        "discipline": "Structures",
    }
    r = await env.client.post("/api/v1/event-logs", json=payload, headers=ENG)
    assert r.status_code == 403

    r = await env.client.post(
        "/api/v1/event-logs", json={**payload, "project_id": env.p1}, headers=ENG
    )
    assert r.status_code == 201

    r = await env.client.patch(
        f"/api/v1/event-logs/{env.e2}", json={"description": "hax"}, headers=ENG
    )
    assert r.status_code == 403
    r = await env.client.delete(f"/api/v1/event-logs/{env.e2}", headers=ENG)
    assert r.status_code == 403

    r = await env.client.patch(
        f"/api/v1/event-logs/{env.e2}", json={"description": "director edit"}, headers=DIR
    )
    assert r.status_code == 200


async def test_hrb_register_is_scoped_and_writes_guarded(env: Env) -> None:
    r = await env.client.get("/api/v1/hrb", headers=ENG)
    assert r.status_code == 200
    assert {row["project_id"] for row in r.json()} == {env.p1}

    r = await env.client.get("/api/v1/hrb", headers=DIR)
    assert len(r.json()) == 2

    r = await env.client.post(
        "/api/v1/hrb", json={"project_id": env.p2, "is_high_risk": True}, headers=ENG
    )
    assert r.status_code == 403

    r = await env.client.patch(
        f"/api/v1/hrb/{env.h2}", json={"is_high_risk": True}, headers=ENG
    )
    assert r.status_code == 403
    r = await env.client.delete(f"/api/v1/hrb/{env.h2}", headers=ENG)
    assert r.status_code == 403

    r = await env.client.delete(f"/api/v1/hrb/{env.h2}", headers=DIR)
    assert r.status_code == 204


async def test_buildings_are_project_scoped(env: Env) -> None:
    r = await env.client.get(f"/api/v1/projects/{env.p1}/buildings", headers=ENG)
    assert r.status_code == 200

    r = await env.client.get(f"/api/v1/projects/{env.p2}/buildings", headers=ENG)
    assert r.status_code == 403

    r = await env.client.post(
        f"/api/v1/projects/{env.p2}/buildings", json={"name": "Block X"}, headers=ENG
    )
    assert r.status_code == 403
    # Nothing was created (and therefore no J: folder task was enqueued).
    r = await env.client.get(f"/api/v1/projects/{env.p2}/buildings", headers=DIR)
    assert [b["name"] for b in r.json()] == ["Main building"]

    r = await env.client.post(
        f"/api/v1/projects/{env.p1}/buildings", json={"name": "Block A"}, headers=ENG
    )
    assert r.status_code == 201


async def test_overview_requires_view_all(env: Env) -> None:
    r = await env.client.get("/api/v1/overview", headers=ENG)
    assert r.status_code == 403
    r = await env.client.get("/api/v1/overview", headers=DIR)
    assert r.status_code == 200


async def test_event_log_mine_scope(env: Env) -> None:
    # Engineer logs an event on their own project.
    r = await env.client.post(
        "/api/v1/event-logs",
        json={
            "project_id": env.p1,
            "description": "my own event",
            "category_of_impact": "Cost",
            "discipline": "Structures",
        },
        headers=ENG,
    )
    assert r.status_code == 201

    # mine=true returns ONLY events this user logged — not the pre-seeded e1
    # (logged_by=None) on the same project, nor the foreign e2.
    r = await env.client.get("/api/v1/event-logs?mine=true", headers=ENG)
    assert r.status_code == 200
    assert [e["description"] for e in r.json()] == ["my own event"]

    # A director's personal view is empty — they logged nothing here.
    r = await env.client.get("/api/v1/event-logs?mine=true", headers=DIR)
    assert r.status_code == 200
    assert r.json() == []


async def test_hrb_mine_scope(env: Env) -> None:
    # Engineer records an HRB determination on their own project.
    r = await env.client.post(
        "/api/v1/hrb",
        json={"project_id": env.p1, "is_high_risk": True},
        headers=ENG,
    )
    assert r.status_code == 201

    r = await env.client.get("/api/v1/hrb?mine=true", headers=ENG)
    assert r.status_code == 200
    assert {row["project_id"] for row in r.json()} == {env.p1}

    r = await env.client.get("/api/v1/hrb?mine=true", headers=DIR)
    assert r.status_code == 200
    assert r.json() == []
