"""Scan J: for each construction (CMAP-5) job's Building Control pack and write
the best-effort result into the qa_building_control index.

READ-ONLY on J:. The folder/file naming is wildly inconsistent across jobs, so
this is a *hint* — "found" = inside <job>\\4 Calculations there is either a
subfolder whose name contains "building control", or a file (bounded recursive)
named with "building control" + a pack/calc/submission qualifier. A director
confirms/overrides per job; the scan never auto-flips a manual decision.

Designed to run in-process (CLI now, scheduled on the J:-connected VM later).
On the VM use the UNC path, not a mapped drive letter.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import building_control as bc_repo
from app.repositories import projects as projects_repo

CALC_FOLDER = "4 Calculations"
BC_ANCHOR = "building control"
BC_FILE_QUALIFIERS = ("pack", "calc", "submission")
FILE_WALK_DEPTH = 3


def is_cmap5(project: Any) -> bool:
    """A construction job per CMAP — its cmap_stage names 'construction'."""
    return bool(project.cmap_stage and "construction" in project.cmap_stage.lower())


def match_job_folders(top_folders: list[Path], number: str) -> list[Path]:
    pattern = re.compile(rf"{re.escape(number)}(?=\D|$)")
    return [p for p in top_folders if pattern.match(p.name)]


def _folder_hit(calc: Path) -> str | None:
    try:
        for sub in calc.iterdir():
            if sub.is_dir() and BC_ANCHOR in sub.name.lower():
                return sub.name
    except OSError:
        return None
    return None


def _file_hit(calc: Path) -> str | None:
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
    """(status, detail) — folder check first (cheap), file walk only if needed."""
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


async def run_scan(session: AsyncSession, root: str | Path) -> dict[str, int]:
    """Scan every CMAP-5 job and upsert results. Jobs with no matching J: folder
    are skipped (no row) — per the practice decision to ignore them. Returns a
    {status: count} summary."""
    root = Path(root)
    top_folders = [p for p in root.iterdir() if p.is_dir()]
    projects = await projects_repo.list_active(session)
    jobs = [p for p in projects if is_cmap5(p)]

    counts: dict[str, int] = {}
    now = datetime.now(UTC)
    for p in jobs:
        folders = match_job_folders(top_folders, p.number)
        if not folders:
            counts["no-job-folder"] = counts.get("no-job-folder", 0) + 1
            continue

        best: tuple[str, str, Path] | None = None
        for jf in folders:
            status, detail = scan_job(jf)
            if status.startswith("found"):
                best = (status, detail, jf)
                break
            if best is None:
                best = (status, detail, jf)
        assert best is not None
        status, detail, jf = best

        await bc_repo.upsert_scan(
            session,
            project_id=p.id,
            scan_detected=status.startswith("found"),
            scan_status=status,
            scan_detail=detail,
            scan_path=str(jf),
            scanned_at=now,
        )
        counts[status] = counts.get(status, 0) + 1

    return counts
