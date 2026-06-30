from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import (
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPkMixin
from app.models.building import Building
from app.models.form import QaFormDefinition
from app.models.project import Project
from app.models.stage import Stage
from app.models.user import User


class QaProjectResponse(UUIDPkMixin, TimestampMixin, Base):
    """All responses for one building on one stage's form (flat JSON by question id).

    QA is scoped to a building, not directly to a project. Single-building
    projects have one (implicit) "Main building"; project_id is kept denormalised
    so the project-level dashboards can roll up across a project's buildings.
    """

    __tablename__ = "qa_project_responses"
    __table_args__ = (
        UniqueConstraint("building_id", "form_id", name="uq_response_building_form"),
        Index("ix_response_building_stage", "building_id", "stage_id"),
        Index("ix_response_project_stage", "project_id", "stage_id"),
        Index("ix_response_completion", "completion_percentage"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    building_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False
    )
    form_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("qa_form_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stages.id", ondelete="CASCADE"), nullable=False
    )

    responses: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    completion_percentage: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    answered_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    reminder_sent_offsets: Mapped[list[int]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    last_updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    project: Mapped[Project] = relationship("Project")
    building: Mapped[Building] = relationship("Building")
    form: Mapped[QaFormDefinition] = relationship("QaFormDefinition")
    stage: Mapped[Stage] = relationship("Stage")
    last_updated_by: Mapped[User | None] = relationship("User")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<QaProjectResponse project={self.project_id} stage={self.stage_id}>"
