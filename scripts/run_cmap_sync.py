"""Run the daily CMAP sync (users + projects) into the Project QA database.

Auth + config come from settings (CMAP_CLIENT_ID / CMAP_CLIENT_SECRET etc. in
.env). Start with a dry run to confirm the field mapping against the live API:

    python scripts/run_cmap_sync.py --dry-run --limit 5   # inspect, write nothing
    python scripts/run_cmap_sync.py                        # full sync

On the J:-connected VM this is what the scheduled (Windows Task Scheduler) job
calls once a day.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.services.cmap_sync import run_sync  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="fetch + map but write nothing"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="cap records fetched per entity"
    )
    args = parser.parse_args()

    if not settings.cmap_enabled:
        print(
            "CMAP is not configured — set CMAP_CLIENT_ID and CMAP_CLIENT_SECRET "
            "in projectqa-api/.env.",
            file=sys.stderr,
        )
        sys.exit(1)

    async with SessionLocal() as session:
        summary = await run_sync(session, dry_run=args.dry_run, limit=args.limit)

    s = summary
    suffix = " (DRY RUN — nothing written)" if s.dry_run else ""
    print(f"\n=== CMAP sync{suffix}", file=sys.stderr)
    print(
        f"users    : seen={s.users_seen} created={s.users_created} "
        f"updated={s.users_updated} skipped={s.users_skipped}",
        file=sys.stderr,
    )
    print(
        f"projects : seen={s.projects_seen} created={s.projects_created} "
        f"updated={s.projects_updated} skipped={s.projects_skipped}",
        file=sys.stderr,
    )
    print(f"unresolved director/manager refs: {s.unresolved_people}", file=sys.stderr)
    # The first dry run confirms the real CMap field names → finalise the mapping.
    if s.sample_user_keys:
        print(f"\nsample USER keys   : {', '.join(s.sample_user_keys)}", file=sys.stderr)
    if s.sample_project_keys:
        print(f"sample PROJECT keys: {', '.join(s.sample_project_keys)}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
