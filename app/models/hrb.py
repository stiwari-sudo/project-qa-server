from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPkMixin
from app.models.project import Project
from app.models.stage import Stage
from app.models.user import User


class QaHighRiskBuilding(UUIDPkMixin, TimestampMixin, Base):
    """High-Risk-Building (Building Safety Act 2022) status per project per stage."""

    __tablename__ = "qa_high_risk_buildings"
    __table_args__ = (
        UniqueConstraint("project_id", "stage_id", name="uq_hrb_project_stage"),
        Index("ix_hrb_is_high_risk", "is_high_risk"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    stage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stages.id", ondelete="SET NULL"), nullable=True
    )
    is_high_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    checked_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[Project] = relationship("Project")
    stage: Mapped[Stage | None] = relationship("Stage")
    checked_by: Mapped[User | None] = relationship("User")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<QaHighRiskBuilding project={self.project_id} hrb={self.is_high_risk}>"
