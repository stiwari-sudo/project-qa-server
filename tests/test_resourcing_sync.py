"""Resourcing membership sync — reconcile logic against a throwaway database
(skips when no Postgres is reachable on the dev cluster)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.repositories import project_members as members_repo
from app.services.resourcing_sync import run_sync

_HOST = "127.0.0.1:5544"
_ADMIN_URL = f"postgresql+asyncpg://qa@{_HOST}/postgres"
_TEST_DB = "projectqa_resourcing_test"
_TEST_URL = f"postgresql+asyncpg://qa@{_HOST}/{_TEST_DB}"


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
        pytest.skip(f"no Postgres reachable on {_HOST} for the resourcing test DB")
    engine = create_async_engine(_TEST_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_sync_reconciles_members_and_preserves_manual(session_factory: Any) -> None:
    async with session_factory() as s:
        u1 = User(email="eng1@hts.uk.com", display_name="Eng One", roles=["engineer"])
        u2 = User(email="eng2@hts.uk.com", display_name="Eng Two", roles=["engineer"])
        s.add_all([u1, u2])
        await s.flush()
        p1 = Project(number="2001", name="Job One")
        p2 = Project(number="2002", name="Job Two")
        s.add_all([p1, p2])
        await s.flush()
        # A manually-granted membership (must survive) + a stale resourcing one.
        s.add(ProjectMember(project_id=p1.id, user_id=u1.id, source="manual"))
        s.add(ProjectMember(project_id=p2.id, user_id=u2.id, source="resourcing"))
        await s.commit()
        p1id, p2id, u1id, u2id = p1.id, p2.id, u1.id, u2.id

    feed = [
        {"project_number": "2001", "employee_email": "Eng1@hts.uk.com"},  # exists (manual)
        {"project_number": "2002", "employee_email": "eng1@hts.uk.com"},  # new resourcing
        {"project_number": "9999", "employee_email": "eng1@hts.uk.com"},  # unknown project
        {"project_number": "2001", "employee_email": "ghost@hts.uk.com"},  # unknown user
    ]
    async with session_factory() as s:
        summary = await run_sync(s, feed=feed)

    assert summary.added == 1  # (p2, u1)
    assert summary.removed == 1  # stale (p2, u2)
    assert summary.unresolved_projects == {"9999"}
    assert summary.unresolved_users == {"ghost@hts.uk.com"}

    async with session_factory() as s:
        all_pairs = await members_repo.list_pairs(s)
        resourcing_pairs = await members_repo.list_pairs(s, "resourcing")
    assert (p1id, u1id) in all_pairs  # manual survived
    assert (p1id, u1id) not in resourcing_pairs  # …and stayed "manual"
    assert (p2id, u2id) not in all_pairs  # stale resourcing removed
    assert (p2id, u1id) in resourcing_pairs  # new resourcing added


async def test_sync_dry_run_writes_nothing(session_factory: Any) -> None:
    async with session_factory() as s:
        u = User(email="x@hts.uk.com", display_name="X", roles=["engineer"])
        s.add(u)
        await s.flush()
        s.add(Project(number="3001", name="J"))
        await s.commit()

    feed = [{"project_number": "3001", "employee_email": "x@hts.uk.com"}]
    async with session_factory() as s:
        summary = await run_sync(s, feed=feed, dry_run=True)
        assert summary.added == 1 and summary.dry_run is True

    async with session_factory() as s:
        assert await members_repo.list_pairs(s) == set()
