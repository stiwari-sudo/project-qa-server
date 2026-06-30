from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.event_log import Discipline
from app.schemas.common import OrmBase


class EventLogOut(OrmBase):
    id: uuid.UUID
    project_id: uuid.UUID
    project_number: str
    project_name: str
    description: str
    cause_reason: str | None = None
    action_effect: str | None = None
    category_of_impact: str
    stage_id: uuid.UUID | None = None
    stage_name: str | None = None
    discipline: Discipline
    logged_by_id: uuid.UUID | None = None
    logged_by_name: str | None = None
    created_at: datetime
    updated_at: datetime


class EventLogCreate(BaseModel):
    project_id: uuid.UUID
    description: str
    cause_reason: str | None = None
    action_effect: str | None = None
    category_of_impact: str
    stage_id: uuid.UUID | None = None
    discipline: Discipline


class EventLogUpdate(BaseModel):
    description: str | None = None
    cause_reason: str | None = None
    action_effect: str | None = None
    category_of_impact: str | None = None
    stage_id: uuid.UUID | None = None
    discipline: Discipline | None = None


class AnalysisBucket(OrmBase):
    key: str
    count: int


class EventLogAnalysis(OrmBase):
    total: int
    by_discipline: list[AnalysisBucket]
    by_category: list[AnalysisBucket]
    by_stage: list[AnalysisBucket]
