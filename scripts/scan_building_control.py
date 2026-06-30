"""Discovery scan: Building Control pack presence on J: for CMAP stage-5 jobs.

READ-ONLY. Never creates, renames or deletes anything — it only looks.

The real convention (per the practice) is messy: inside each job's "4 Calculations"
folder there's usually a Building Control pack, but the folder name varies a lot
("00 Building Control Pack", "15.0 BUILDING CONTROL CALCULATION PACK",
"19. BUILDING CONTROL PACK", "Building Control Calculation Pack",
"12.0 - Building Control Submission"), and some jobs keep it as loose files instead.
The common thread is the words "Building Control".

So "found" = inside <job>\4 Calculations, EITHER:
  - a subfolder whose name contains "building control", OR
  - a file (bounded recursive) whose name contains "building control" AND one of
    pack / calc / submission (the qualifier avoids matching stray emails etc.).

Run (from projectqa-api/, with the venv python):
    python scripts/scan_building_control.py --limit 20   # quick sample
    python scripts/scan_building_control.py               # all CMAP-5 jobs
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import SessionLocal  # noqa: E402
from app.repositories import projects as projects_repo  # noqa: E402

CALC_FOLDER = "4 Calculations"
BC_ANCHOR = "building control"
BC_FILE_QUALIFIERS = ("pack", "calc", "submission")
FILE_WALK_DEPTH = 3


def list_top_folders(root: Path) -> list[Path]:
    try:
        return [p for p in root.iterdir() if p.is_dir()]
    except OSError as exc:  # pragma: no cover - environment dependent
        print(f"Cannot list {root}: {exc}", file=sys.stderr)
        return []


def match_job_folders(top_folders: list[Path], number: str) -> list[Path]:
    pattern = re.compile(rf"{re.escape(number)}(?=\D|$)")
    return [p for p in top_folders if pattern.match(p.name)]


def _folder_hit(calc: Path) -> str | None:
    """An immediate subfolder of 4 Calculations named like a Building Control pack."""
    try:
        for sub in calc.iterdir():
            if sub.is_dir() and BC_ANCHOR in sub.name.lower():
                return sub.name
    except OSError:
        return None
    return None


def _file_hit(calc: Path) -> str | None:
    """A file (bounded recursive) named with 'building control' + a pack/calc qualifier."""
    base = len(calc.parts)
    for dirpath, dirnames, filenames in os.walk(calc):
        if len(Path(dirpath).parts) - base >= FILE_WALK_DEPTH:
            dirnames[:] = []
            continue
        for fname in filenames:
            low = fname.lower()
            if BC_ANCHOR in low and any(q in low for q in BC_FILE_QUALIFIERS):
                return fname
    return None


def scan_job(job_folder: Path) -> tuple[str, str]:
    """(status, detail) for a job. Folder check first (cheap); file walk only if needed."""
    calc = job_folder / CALC_FOLDER
    try:
        if not calc.is_dir():
            return "no-4-calculations", f"no '{CALC_FOLDER}' folder"
    except OSError as exc:
        return "error", str(exc)

    folder = _folder_hit(calc)
    if folder:
        return "found-folder", f"folder='{folder}'"
    file = _file_hit(calc)
    if file:
        return "found-file", f"file='{file}'"
    return "not-found", "no Building Control folder or pack file in 4 Calculations"


async def load_cmap5_jobs() -> list:
    async with SessionLocal() as session:
        projects = await projects_repo.list_active(session)
    return [
        p for p in projects if p.cmap_stage and "construction" in p.cmap_stage.lower()
    ]


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="J:\\", help="J: drive root (default J:\\)")
    parser.add_argument("--limit", type=int, default=0, help="scan only the first N jobs")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).with_name("building-control-scan.csv")),
        help="output CSV path",
    )
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"Root {root} is not accessible.", file=sys.stderr)
        sys.exit(1)

    print("Listing J: top-level folders…", file=sys.stderr)
    top_folders = list_top_folders(root)
    print(f"  {len(top_folders)} folders.", file=sys.stderr)

    jobs = await load_cmap5_jobs()
    jobs.sort(key=lambda p: p.number)
    if args.limit:
        jobs = jobs[: args.limit]
    print(f"CMAP stage-5 jobs to scan: {len(jobs)}", file=sys.stderr)

    rows: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    for i, p in enumerate(jobs, 1):
        folders = match_job_folders(top_folders, p.number)
        if not folders:
            status, detail, job_folder = "no-job-folder", "no J: folder matched", ""
        else:
            best: tuple[str, str, str] | None = None
            for jf in folders:
                status, detail = scan_job(jf)
                if status.startswith("found"):
                    best = (status, detail, str(jf))
                    break
                if best is None:
                    best = (status, detail, str(jf))
            assert best is not None
            status, detail, job_folder = best

        counts[status] = counts.get(status, 0) + 1
        rows.append(
            {
                "number": p.number,
                "name": p.name,
                "director": p.director.display_name if p.director else "",
                "manager": p.manager.display_name if p.manager else "",
                "cmap_stage": p.cmap_stage or "",
                "job_folder": job_folder,
                "status": status,
                "detail": detail,
            }
        )
        print(f"  [{i}/{len(jobs)}] {p.number} {p.name[:34]:34} -> {status}", file=sys.stderr)

    with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "number", "name", "director", "manager",
                "cmap_stage", "job_folder", "status", "detail",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    found = sum(v for k, v in counts.items() if k.startswith("found"))
    print("\n=== Building Control pack scan ===", file=sys.stderr)
    print(f"CMAP-5 jobs scanned : {len(jobs)}", file=sys.stderr)
    print(f"FOUND (any signal)  : {found}/{len(jobs)}", file=sys.stderr)
    for status in sorted(counts):
        print(f"  {status:18}: {counts[status]}", file=sys.stderr)
    print(f"\nCSV written to: {args.out}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
