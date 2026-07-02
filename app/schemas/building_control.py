from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BuildingControlOut(BaseModel):
    """A construction job's calc-package status. The verdict (``form_status`` /
    ``present``) is the canonical ``q_*_sd_5`` form answer that the director KPI
    reads; the ``scan_*`` fields are the advisory best-effort J: hint, and
    ``agreement`` says how the two compare."""

    project_id: uuid.UUID
    project_number: str
    project_name: str
    director_name: str | None = None
    manager_name: str | None = None

    # Canonical verdict — the structural calc-package form answer.
    form_status: str  # "yes" | "no" | "blank"
    present: bool  # form_status == "yes"

    # Best-effort J: scan hint (advisory only).
    scanned: bool  # a scan row exists for this job
    scan_detected: bool  # the scan found a calc/Building-Control pack
    scan_status: str | None = None
    scan_path: str | None = None
    scanned_at: datetime | None = None

    # How the scan compares to the form verdict.
    agreement: str  # "match" | "scan_only" | "form_only" | "no_scan"


class BuildingControlSummary(BaseModel):
    """Roll-up across construction jobs: the form verdict spread plus how well the
    J: scan agrees with it."""

    total: int
    present: int  # form says complete
    absent: int  # form explicitly "No"
    blank: int  # not yet answered
    scanned: int  # have a J: scan row
    detected: int  # scan found a pack
    mismatch: int  # scan disagrees with the form verdict


class BuildingControlList(BaseModel):
    summary: BuildingControlSummary
    items: list[BuildingControlOut] = Field(default_factory=list)


class BuildingControlUpdate(BaseModel):
    """Director confirm/override — writes the canonical calc-package form answer
    (``True`` → "Yes", ``False`` → "No")."""

    present: bool
