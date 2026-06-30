"""Run the Building Control J: scan and write results into qa_building_control.

Run (from projectqa-api/, with the venv python):
    python scripts/run_building_control_scan.py                 # scan J:\
    python scripts/run_building_control_scan.py --root \\\\server\\share

On the J:-connected VM this is what the scheduled APScheduler job will call
(via app.services.building_control_scan.run_scan), using the UNC path.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import SessionLocal  # noqa: E402
from app.services.building_control_scan import run_scan  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="J:\\", help="J: drive / UNC root (default J:\\)")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"Root {root} is not accessible.", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {root} for Building Control packs…", file=sys.stderr)
    async with SessionLocal() as session:
        counts = await run_scan(session, root)
        await session.commit()

    found = sum(v for k, v in counts.items() if k.startswith("found"))
    total = sum(counts.values())
    print("\n=== Building Control scan → index ===", file=sys.stderr)
    print(f"jobs processed : {total}", file=sys.stderr)
    print(f"detected       : {found}", file=sys.stderr)
    for status in sorted(counts):
        print(f"  {status:18}: {counts[status]}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
