"""Sync project-team membership from the TechandData resourcing feed.

Config (in .env): RESOURCING_FEED_URL (the /api/resourcing/project-members/
endpoint) and RESOURCING_FEED_KEY (the shared secret, matching the TechandData
PROJECT_QA_FEED_KEY). Start with a dry run:

    python scripts/run_resourcing_sync.py --dry-run   # fetch + reconcile, write nothing
    python scripts/run_resourcing_sync.py             # apply

On the host this is what the daily scheduled job calls.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.services.resourcing_sync import ResourcingError, run_sync  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="reconcile but write nothing")
    args = parser.parse_args()

    if not settings.resourcing_enabled:
        print(
            "Resourcing feed is not configured — set RESOURCING_FEED_URL and "
            "RESOURCING_FEED_KEY in projectqa-api/.env.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        async with SessionLocal() as session:
            s = await run_sync(session, dry_run=args.dry_run)
    except ResourcingError as exc:
        print(f"\nResourcing sync failed: {exc}", file=sys.stderr)
        sys.exit(2)

    suffix = " (DRY RUN — nothing written)" if s.dry_run else ""
    print(f"\n=== Resourcing membership sync{suffix}", file=sys.stderr)
    print(
        f"feed rows: {s.feed_rows}  added: {s.added}  removed: {s.removed}  "
        f"unchanged: {s.unchanged}",
        file=sys.stderr,
    )
    if s.unresolved_projects:
        print(
            f"unresolved project numbers ({len(s.unresolved_projects)}): "
            f"{', '.join(sorted(s.unresolved_projects)[:15])}",
            file=sys.stderr,
        )
    if s.unresolved_users:
        print(
            f"unresolved emails ({len(s.unresolved_users)}): "
            f"{', '.join(sorted(s.unresolved_users)[:15])}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    asyncio.run(main())
