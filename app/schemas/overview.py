from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class IncompleteProject(BaseModel):
    project_id: uuid.UUID
    project_number: str
    project_name: str
    manager_name: str | None = None


class DirectorBucket(BaseModel):
    director_id: uuid.UUID | None = None
    director_name: str
    construction_project_count: int
    calc_package_complete_count: int
    calc_package_completion_pct: float
    incomplete_projects: list[IncompleteProject] = Field(default_factory=list)


class OverviewTotals(BaseModel):
    construction_project_count: int
    calc_package_complete_count: int
    calc_package_completion_pct: float


class OverviewOut(BaseModel):
    directors: list[DirectorBucket]
    totals: OverviewTotals
