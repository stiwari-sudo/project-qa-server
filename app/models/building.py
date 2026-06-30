from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPkMixin
from app.models.project import Project


class Building(UUIDPkMixin, TimestampMixin, Base):
    """A building within a project.

    QA (stage responses, HRB determination, the engineering review list) is
    tracked per building so multi-building projects can be assessed separately.
    Every project has at least one — a default "Main building" — so
    single-building projects need no building step.
    """

    __tablename__ = "buildings"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_building_project_name"),
        Index("ix_building_project", "project_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    project: Mapped[Project] = relationship("Project")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Building project={self.project_id} {self.name!r}>"
