from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPkMixin
from app.models.project import Project
from app.models.stage import Stage
from app.models.user import User


class Discipline(str, enum.Enum):
    STRUCTURES = "Structures"
    CIVILS = "Civils"
    GEOTECHNICAL = "Geotechnical"
    HIGHWAYS = "Highways"
    OTHER = "Other"


class QaEventLog(UUIDPkMixin, TimestampMixin, Base):
    """A significant project QA event (design change, issue, improvement)."""

    __tablename__ = "qa_event_logs"
    __table_args__ = (
        Index("ix_event_project_created", "project_id", "created_at"),
        Index("ix_event_stage_created", "stage_id", "created_at"),
        Index("ix_event_discipline", "discipline"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    cause_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_effect: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_of_impact: Mapped[str] = mapped_column(String(150), nullable=False)

    stage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stages.id", ondelete="SET NULL"), nullable=True
    )
    discipline: Mapped[Discipline] = mapped_column(
        SAEnum(Discipline, name="discipline_enum"), nullable=False
    )
    logged_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    project: Mapped[Project] = relationship("Project")
    stage: Mapped[Stage | None] = relationship("Stage")
    logged_by: Mapped[User | None] = relationship("User")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<QaEventLog project={self.project_id} {self.discipline}>"
