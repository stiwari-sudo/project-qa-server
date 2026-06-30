from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.schemas.building_control import BuildingControlSummary


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


class DirectorCompletion(BaseModel):
    """Detailed QA: average QA-form completion across all of a director's
    active projects (every stage, not just construction)."""

    director_id: uuid.UUID | None = None
    director_name: str
    project_count: int
    avg_completion_pct: float


class OverviewTotals(BaseModel):
    construction_project_count: int
    calc_package_complete_count: int
    calc_package_completion_pct: float


class StageCount(BaseModel):
    """One bucket of a stage distribution (a stage name + how many projects)."""

    stage_name: str
    project_count: int


class BasicQaCheck(BaseModel):
    """Legacy "Basic QA Check": a project has responded once any question is
    answered "Yes" (any variant). ``response_rate`` = has ÷ total × 100."""

    has_responses: int
    no_responses: int
    response_rate: float


class DirectorAnalysisRow(BaseModel):
    """Per-director portfolio health, ported from the legacy Director Analysis
    dashboard: response rate, average completion, and QA/CMAP stage spread."""

    director_id: uuid.UUID | None = None
    director_name: str
    total_projects: int
    basic_qa_check: BasicQaCheck
    completion_rate: float
    qa_stage_distribution: list[StageCount] = Field(default_factory=list)
    cmap_stage_distribution: list[StageCount] = Field(default_factory=list)


class AnalysisTotals(BaseModel):
    """Practice-wide rollup of the director analysis (executive KPIs)."""

    total_directors: int
    total_projects: int
    has_responses: int
    no_responses: int
    response_rate: float
    avg_completion_rate: float


class OverviewOut(BaseModel):
    directors: list[DirectorBucket]
    completion_by_director: list[DirectorCompletion] = Field(default_factory=list)
    totals: OverviewTotals
    # Director Analysis (ported from legacy): response rate + stage distributions.
    director_analysis: list[DirectorAnalysisRow] = Field(default_factory=list)
    qa_stage_distribution: list[StageCount] = Field(default_factory=list)
    cmap_stage_distribution: list[StageCount] = Field(default_factory=list)
    analysis_totals: AnalysisTotals | None = None
    # Building Control pack coverage across scanned construction jobs.
    building_control: BuildingControlSummary | None = None
