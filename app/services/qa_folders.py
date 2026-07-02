r"""Scaffold a new building's folder structure on the QA file share.

When an *extra* building (one beyond the project's primary "Main building") is
added in the app, we mirror the project's QA layout under a per-building parent
folder so each building's QA is kept separate on J::

    <job>\10 QA\<building>\<stage>\           each stage gets the full evidence tree
        Peer Review\  (Peer Site Visit, Informal QA, Temporary Works Design)
        Structural Design\
        Civil Design\
        Highways and Transport Design\
        Geotechnical Design\
        Information Output\
    <job>\4 Calculations\<building>\          just the building parent folder

Best-effort and idempotent: additive only (never deletes/renames), skips folders
that already exist, and swallows every error — a share hiccup must never fail the
building's creation. Runs as a background task; when no share root is configured
(local dev) it's a silent no-op. Mirrors scripts/Create-QaEvidenceFolders.ps1 —
keep the two structures in step.

On the J:-connected VM point QA_SHARE_ROOT at the UNC root, not a mapped drive
letter (per-user, invisible to a service account).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import BackgroundTasks

from app.core.config import settings

logger = logging.getLogger(__name__)

QA_FOLDER = "10 QA"
CALC_FOLDER = "4 Calculations"

# The evidence structure created inside every QA stage folder — mirror of the
# PowerShell script's $StageSubfolders / $PeerReviewChildren.
STAGE_SUBFOLDERS = (
    "Peer Review",
    "Structural Design",
    "Civil Design",
    "Highways and Transport Design",
    "Geotechnical Design",
    "Information Output",
)
PEER_REVIEW_CHILDREN = (
    "Peer Site Visit",
    "Informal QA",
    "Temporary Works Design",
)
# Fallback stage set (template names) used only when the project's "10 QA" has no
# existing 10.x stage folders to mirror. Real projects already have all six.
CANONICAL_STAGES = (
    "10.1 Concept Design",
    "10.2 Detailed Design",
    "10.3 Pre-Tender",
    "10.4 Pre-Construction",
    "10.5 Site",
    "10.6 Archive",
)

_STAGE_RE = re.compile(r"^10\.\d")
# Characters Windows forbids in a path segment (building names are user-entered).
_ILLEGAL_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_segment(name: str) -> str:
    """A filesystem-safe folder name from a user-entered building name — strips
    forbidden characters and trailing dots/spaces (invalid on Windows)."""
    return _ILLEGAL_RE.sub("", name).strip().rstrip(". ")


def _resolve_job_folder(root: Path, number: str) -> Path | None:
    """Find the project's top-level job folder by its number prefix (the same
    match the Building Control scan uses). Prefer a match that actually has a
    "10 QA" folder so e.g. "10" doesn't grab "100 …"."""
    pattern = re.compile(rf"{re.escape(number)}(?=\D|$)")
    try:
        matches = [p for p in root.iterdir() if p.is_dir() and pattern.match(p.name)]
    except OSError as exc:
        logger.warning("Could not list share root %s: %s", root, exc)
        return None
    if not matches:
        return None
    with_qa = [p for p in matches if (p / QA_FOLDER).is_dir()]
    return (with_qa or matches)[0]


def _existing_stage_names(qa: Path) -> list[str]:
    """The project's existing 10.x stage folder names, so the building's stages
    mirror the project's own naming/casing rather than a fixed template."""
    try:
        return sorted(
            p.name for p in qa.iterdir() if p.is_dir() and _STAGE_RE.match(p.name)
        )
    except OSError:
        return []


def _ensure(path: Path, summary: dict[str, int]) -> None:
    """Create ``path`` (and parents) if missing; tally the outcome. Idempotent."""
    if path.exists():
        summary["exists"] += 1
        return
    try:
        path.mkdir(parents=True, exist_ok=True)
        summary["created"] += 1
    except OSError as exc:
        logger.warning("Could not create %s: %s", path, exc)
        summary["error"] += 1


def scaffold_building_folders(
    root: Path, project_number: str, building_name: str
) -> dict[str, int]:
    """Create the per-building QA + calc folders under the job on the share.

    Returns a {created, exists, error} summary. Never raises.
    """
    summary: dict[str, int] = {"created": 0, "exists": 0, "error": 0}

    building = _safe_segment(building_name)
    if not building:
        logger.warning(
            "Skipping folder scaffold: building name %r has no usable characters",
            building_name,
        )
        return summary

    job = _resolve_job_folder(root, project_number)
    if job is None:
        logger.info(
            "Skipping folder scaffold: no job folder matching %s under %s",
            project_number,
            root,
        )
        return summary

    # QA side — mirror the project's stage folders under the building parent and
    # fill each with the full evidence tree. mkdir(parents=True) creates the
    # building + stage folders implicitly.
    qa = job / QA_FOLDER
    if qa.is_dir():
        stages = _existing_stage_names(qa) or list(CANONICAL_STAGES)
        for stage in stages:
            stage_dir = qa / building / stage
            for sub in STAGE_SUBFOLDERS:
                _ensure(stage_dir / sub, summary)
            for child in PEER_REVIEW_CHILDREN:
                _ensure(stage_dir / "Peer Review" / child, summary)
    else:
        logger.info("No '%s' folder in %s — skipping QA scaffold", QA_FOLDER, job)

    # Calculations side — just the building parent folder.
    _ensure(job / CALC_FOLDER / building, summary)

    logger.info(
        "Folder scaffold for building %r (project %s) at %s: %s",
        building,
        project_number,
        job,
        summary,
    )
    return summary


def _run_scaffold(root: str, project_number: str, building_name: str) -> None:
    try:
        scaffold_building_folders(Path(root), project_number, building_name)
    except Exception:  # pragma: no cover - defensive; scaffold already guards
        logger.exception(
            "Folder scaffold crashed for building %r (project %s)",
            building_name,
            project_number,
        )


def enqueue_building_folders(
    background_tasks: BackgroundTasks,
    project_number: str,
    building_name: str,
) -> None:
    """Schedule best-effort folder scaffolding for a newly added building. A
    no-op when no share root is configured (local dev)."""
    root = settings.qa_share_root.strip()
    if not root:
        return
    background_tasks.add_task(_run_scaffold, root, project_number, building_name)
