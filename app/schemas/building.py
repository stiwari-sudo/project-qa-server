from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import OrmBase


class BuildingOut(OrmBase):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    order: int
    created_at: datetime
    updated_at: datetime


class BuildingCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    order: int | None = None
