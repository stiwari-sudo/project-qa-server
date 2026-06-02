from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import OrmBase


class InputType(str, enum.Enum):
    DROPDOWN = "dropdown"
    TEXT = "text"
    TEXTAREA = "textarea"
    NUMBER = "number"
    DATE = "date"
    FILE = "file"
    YES_NO = "yes_no"


class QuestionSchema(BaseModel):
    """A single question in the JSON form structure (may carry one subform)."""

    id: str
    text: str
    task_number: str | None = None
    input_type: InputType
    options: list[str] = Field(default_factory=list)
    help_text: str | None = None
    # Marks the single Building-Safety-Act question used for HRB sync.
    hrb_flag: bool = False
    has_subform: bool = False
    trigger_value: str | None = None
    subform: SubformSchema | None = None


class SubformSchema(BaseModel):
    id: str
    questions: list[QuestionSchema] = Field(default_factory=list)


class SectionSchema(BaseModel):
    id: str
    title: str
    order: int
    questions: list[QuestionSchema] = Field(default_factory=list)


class FormStructureSchema(BaseModel):
    """Validated on write — the canonical sections -> questions -> subform shape."""

    sections: list[SectionSchema] = Field(default_factory=list)


QuestionSchema.model_rebuild()


# ---- API in/out ----


class FormListItem(OrmBase):
    id: uuid.UUID
    name: str
    version: int
    is_active: bool
    stage_id: uuid.UUID
    stage_name: str
    question_count: int


class FormOut(OrmBase):
    id: uuid.UUID
    name: str
    version: int
    is_active: bool
    stage_id: uuid.UUID
    stage_name: str
    structure: FormStructureSchema
    question_count: int
    created_at: datetime
    updated_at: datetime


class FormCreate(BaseModel):
    name: str
    stage_id: uuid.UUID
    version: int = 1
    is_active: bool = True
    structure: FormStructureSchema
