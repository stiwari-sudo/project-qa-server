from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import OrmBase


class ResponseOut(OrmBase):
    id: uuid.UUID
    project_id: uuid.UUID
    project_number: str
    project_name: str
    form_id: uuid.UUID
    form_name: str
    stage_id: uuid.UUID
    stage_name: str
    responses: dict[str, Any]
    completion_percentage: float
    total_questions: int
    answered_questions: int
    deadline: date | None = None
    reminder_sent_offsets: list[int] = Field(default_factory=list)
    last_updated_by_id: uuid.UUID | None = None
    last_updated_by_name: str | None = None
    created_at: datetime
    updated_at: datetime


class BulkSaveIn(BaseModel):
    """Bulk save: map of {question_id: raw_value} plus an optional deadline."""

    responses: dict[str, Any] = Field(default_factory=dict)
    deadline: date | None = None
