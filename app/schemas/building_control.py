from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BuildingControlOut(BaseModel):
    """A construction job's Building Control pack status — the best-effort J:
    scan hint plus any director confirm/override, reduced to one
    ``effective_status``."""

    project_id: uuid.UUID
    project_number: str
    project_name: str
    director_name: str | None = None
    manager_name: str | None = None

    # Best-effort J: scan hint.
    scan_detected: bool
    # found-folder | found-file | not-found | no-4-calculations | error
    scan_status: str | None = None
    scan_detail: str | None = None
    scan_path: str | None = None
    scanned_at: datetime | None = None

    # Director confirm/override and the resulting effective status.
    manual_status: str | None = None  # "found" | "not_found" | None (defer to scan)
    effective_status: str  # "found" | "not_found" | "unknown"
    confirmed_by_name: str | None = None
    notes: str | None = None
    updated_at: datetime


class BuildingControlSummary(BaseModel):
    """At-a-glance counts across the scanned construction jobs."""

    total: int
    found: int
    not_found: int
    unknown: int
    # How many verdicts are a director's confirm/override (vs. scan-only hint).
    confirmed: int
    found_pct: float


class BuildingControlList(BaseModel):
    summary: BuildingControlSummary
    items: list[BuildingControlOut] = Field(default_factory=list)


class BuildingControlUpdate(BaseModel):
    """Director confirm/override. ``manual_status=None`` clears the override and
    defers to the scan hint again."""

    manual_status: str | None = None  # "found" | "not_found" | None
    notes: str | None = Field(default=None, max_length=2000)
