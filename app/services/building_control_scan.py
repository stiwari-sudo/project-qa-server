"""Scan J: for each construction (CMAP-5) job's structural calc / Building Control
pack and write the best-effort result into the qa_building_control index.

READ-ONLY on J:. The folder/file naming is wildly inconsistent across jobs, so
this is a *hint* — "found" = inside <job>\\4 Calculations there is either a
subfolder whose name contains "calc pack" / "calculation pack" / "building
control", or a file (bounded recursive) named likewise. The canonical verdict is
the director/engineer's form answer; the scan only suggests and flags mismatches.

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
# A subfolder/file name signals the structural calc package if it names a calc
# pack or a Building Control pack — the same artifact, named inconsistently
# across jobs ("99 Calc Pack", "Calculation packs", "Building Control Pack", …).
FOLDER_ANCHORS = ("building control", "calc pack", "calculation pack")
# Bare "building control" files need a pack/calc/submission qualifier to avoid
# matching stray emails; "calc pack"/"calculation pack" are specific on their own.
BC_FILE_QUALIFIERS = ("pack", "calc", "submission")
FILE_WALK_DEPTH = 3


def _name_is_pack_folder(name: str) -> bool:
    low = name.lower()
    return any(anchor in low for anchor in FOLDER_ANCHORS)


def _name_is_pack_file(name: str) -> bool:
    low = name.lower()
    if "calc pack" in low or "calculation pack" in low:
        return True
    return "building control" in low and any(q in low for q in BC_FILE_QUALIFIERS)


def is_cmap5(project: Any) -> bool:
    """A construction job per CMAP — its cmap_stage names 'construction'."""
    return bool(project.cmap_stage and "construction" in project.cmap_stage.lower())


def match_job_folders(top_folders: list[Path], number: str) -> list[Path]:
    pattern = re.compile(rf"{re.escape(number)}(?=\D|$)")
    return [p for p in top_folders if pattern.match(p.name)]


def _folder_hit(calc: Path) -> str | None:
    try:
        for sub in calc.iterdir():
            if sub.is_dir() and _name_is_pack_folder(sub.name):
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
            if _name_is_pack_file(fname):
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

        # The pack lives inside the job's "4 Calculations" folder, so point the
        # UI's path there (that's where a director looks). Fall back to the job
        # folder only when there's no calculations folder to point at.
        calc = jf / CALC_FOLDER
        scan_path = str(jf) if status in ("no-4-calculations", "error") else str(calc)

        await bc_repo.upsert_scan(
            session,
            project_id=p.id,
            scan_detected=status.startswith("found"),
            scan_status=status,
            scan_detail=detail,
            scan_path=scan_path,
            scanned_at=now,
        )
        counts[status] = counts.get(status, 0) + 1

    return counts
