"""Populate Project.cmap_stage from the legacy QA v2 DB.

The legacy `project_qa_projectqalateststage` table holds each project's current
CMAP stage (a RIBA-style name like "5 - Construction"). The original migration
brought across `cmap_ref` but not this stage; this fills it in so the app can
compare the CMAP stage against the latest QA stage. Idempotent — re-run anytime.

Run (from projectqa-api/, MySQL + PG cluster up):

    ./.venv/Scripts/python.exe -m scripts.sync_cmap_stages
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.project import Project
from scripts.migrate_legacy import _mysql


def _legacy_cmap_stages() -> dict[str, str]:
    """Map our project number -> CMAP stage name from the legacy DB."""
    conn = _mysql()
    cur = conn.cursor()
    cur.execute(
        "SELECT pp.number AS number, ls.project_stage AS stage "
        "FROM project_qa_projectqalateststage ls "
        "JOIN projects_project pp ON ls.project_id = pp.id"
    )
    rows = cur.fetchall()
    conn.close()
    return {
        str(r["number"]): str(r["stage"]).strip()
        for r in rows
        if r["stage"] and str(r["stage"]).strip()
    }


async def main() -> None:
    by_number = _legacy_cmap_stages()
    print(f"legacy CMAP stages: {len(by_number)}")
    async with SessionLocal() as session:
        projects = list((await session.execute(select(Project))).scalars().all())
        updated = 0
        matched = 0
        for p in projects:
            stage = by_number.get(p.number)
            if stage is None:
                continue
            matched += 1
            if p.cmap_stage != stage:
                p.cmap_stage = stage
                updated += 1
        await session.commit()
        print(f"matched {matched} of {len(projects)} projects; updated {updated}")


if __name__ == "__main__":
    asyncio.run(main())
