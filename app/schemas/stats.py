from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProjectStageStat(BaseModel):
    stage_id: uuid.UUID
    stage_name: str
    stage_order: int
    form_name: str | None = None
    form_version: int | None = None
    total_questions: int
    answered_questions: int
    completion_percentage: float
    last_updated: datetime | None = None


class StageCompletion(BaseModel):
    stage_id: uuid.UUID
    stage_order: int
    total_questions: int
    answered_questions: int
    completion_percentage: float
    status: str  # "Complete" | "In Progress" | "Not Started"


class AllProjectsStatsRow(BaseModel):
    project_id: uuid.UUID
    project_number: str
    project_name: str
    director_id: uuid.UUID | None = None
    director_name: str | None = None
    manager_id: uuid.UUID | None = None
    manager_name: str | None = None
    latest_qa_stage: str | None = None
    total_questions: int
    total_answered: int
    completion_rate: float
    status: str
    deadline: str | None = None
    last_updated: datetime | None = None
    qa_stage_completion: dict[str, StageCompletion] = Field(default_factory=dict)
