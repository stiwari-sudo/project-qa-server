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
    manager_name: str | None = None
    stage_id: uuid.UUID | None = None
    stage_name: str | None = None
    is_high_risk: bool
    checked_by_id: uuid.UUID | None = None
    checked_by_name: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class HrbCreate(BaseModel):
    project_id: uuid.UUID
    stage_id: uuid.UUID | None = None
    is_high_risk: bool = False
    notes: str | None = None


class HrbUpdate(BaseModel):
    stage_id: uuid.UUID | None = None
    is_high_risk: bool | None = None
    notes: str | None = None
