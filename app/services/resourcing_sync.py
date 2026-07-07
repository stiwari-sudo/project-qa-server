"""Sync project-team membership from the HTS TechandData resourcing feed.

Calls /api/resourcing/project-members/ (server-to-server, gated by a shared
X-Api-Key), maps each {project_number, employee_email} to our project (by
number) and user (by email), and reconciles the "resourcing" rows of
project_members: adds new memberships, removes ones no longer in the feed, and
never touches "manual" rows. Populating project_members is what lets an
own-only engineer see the projects they're resourced on.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.repositories import project_members as members_repo
from app.repositories import projects as projects_repo
from app.repositories import users as users_repo

logger = get_logger(__name__)

SOURCE = "resourcing"


class ResourcingError(RuntimeError):
    """The resourcing feed call failed."""


async def fetch_feed() -> list[dict[str, Any]]:
    """GET the flat [{project_number, employee_email}, ...] membership feed."""
    if not settings.resourcing_enabled:
        raise ResourcingError("RESOURCING_FEED_URL / RESOURCING_FEED_KEY are not set")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            settings.resourcing_feed_url,
            headers={
                "X-Api-Key": settings.resourcing_feed_key,
                "Accept": "application/json",
            },
        )
    if resp.status_code != 200:
        raise ResourcingError(
            f"resourcing feed failed ({resp.status_code}): {resp.text[:200]}"
        )
    data = resp.json()
    if not isinstance(data, list):
        raise ResourcingError("resourcing feed did not return a list")
    return [r for r in data if isinstance(r, dict)]


@dataclass
class SyncSummary:
    feed_rows: int = 0
    added: int = 0
    removed: int = 0
    unchanged: int = 0
    unresolved_projects: set[str] = field(default_factory=set)
    unresolved_users: set[str] = field(default_factory=set)
    dry_run: bool = False


async def run_sync(
    session: AsyncSession,
    *,
    feed: list[dict[str, Any]] | None = None,
    dry_run: bool = False,
) -> SyncSummary:
    """Reconcile resourcing-sourced project_members against the feed. On dry_run
    the transaction is rolled back."""
    rows = feed if feed is not None else await fetch_feed()
    summary = SyncSummary(feed_rows=len(rows), dry_run=dry_run)

    # Resolve the feed to (project_id, user_id) pairs, caching lookups since the
    # same project/employee recurs across rows.
    project_ids: dict[str, uuid.UUID | None] = {}
    user_ids: dict[str, uuid.UUID | None] = {}
    desired: set[tuple[uuid.UUID, uuid.UUID]] = set()

    for row in rows:
        number = str(row.get("project_number") or "").strip()
        email = str(row.get("employee_email") or "").strip().lower()
        if not number or not email:
            continue
        if number not in project_ids:
            project = await projects_repo.get_by_number(session, number)
            project_ids[number] = project.id if project else None
        if email not in user_ids:
            user = await users_repo.get_by_email(session, email)
            user_ids[email] = user.id if user else None
        pid, uid = project_ids[number], user_ids[email]
        if pid is None:
            summary.unresolved_projects.add(number)
            continue
        if uid is None:
            summary.unresolved_users.add(email)
            continue
        desired.add((pid, uid))

    all_current = await members_repo.list_pairs(session)
    resourcing_current = await members_repo.list_pairs(session, SOURCE)

    # Add only pairs that don't exist under ANY source (never duplicate a
    # manually-granted membership); remove only resourcing rows no longer wanted.
    for pid, uid in desired - all_current:
        await members_repo.add(session, pid, uid, source=SOURCE)
        summary.added += 1
    for pid, uid in resourcing_current - desired:
        await members_repo.remove(session, pid, uid)
        summary.removed += 1
    summary.unchanged = len(desired & resourcing_current)

    if dry_run:
        await session.rollback()
    else:
        await session.commit()
    logger.info(
        "resourcing.sync.complete",
        feed_rows=summary.feed_rows,
        added=summary.added,
        removed=summary.removed,
        unchanged=summary.unchanged,
        unresolved_projects=len(summary.unresolved_projects),
        unresolved_users=len(summary.unresolved_users),
        dry_run=dry_run,
    )
    return summary
