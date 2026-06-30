from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import OrmBase


class HrbOut(OrmBase):
    id: uuid.UUID
    project_id: uuid.UUID
    project_number: str
    project_name: str
    building_id: uuid.UUID
    building_name: str
    manager_name: str | None = None
    stage_id: uuid.UUID | None = None
    stage_name: str | None = None
    # QA-form completion % for this project at this stage (matches the stage's
    # completion ring in the project detail view). None when no response exists.
    qa_completion_pct: float | None = None
    is_high_risk: bool
    checked_by_id: uuid.UUID | None = None
    checked_by_name: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class HrbCreate(BaseModel):
    project_id: uuid.UUID
    # Optional: omit for single-building projects (the primary building is used).
    building_id: uuid.UUID | None = None
    stage_id: uuid.UUID | None = None
    is_high_risk: bool = False
    notes: str | None = None


class HrbUpdate(BaseModel):
    stage_id: uuid.UUID | None = None
    is_high_risk: bool | None = None
    notes: str | None = None
