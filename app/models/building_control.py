from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPkMixin
from app.models.project import Project
from app.models.user import User


class QaBuildingControl(UUIDPkMixin, TimestampMixin, Base):
    """Building Control pack status for a construction (CMAP stage-5) project.

    The ``scan_*`` fields are the best-effort J: drive hint (the scanner only
    *suggests* whether a Building Control pack folder/file exists); ``manual_status``
    is a director's confirm/override. The effective status uses the manual value
    when set, else the scan — the scanner never auto-flips a human decision.
    """

    __tablename__ = "qa_building_control"
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_building_control_project"),
        Index("ix_building_control_project", "project_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    # Best-effort J: scan hint.
    scan_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # found-folder | found-file | not-found | no-4-calculations | error
    scan_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    scan_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The job's J: folder, for an "open folder" link in the UI.
    scan_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    scanned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Director confirm/override: "found" | "not_found" | None (= defer to scan).
    manual_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confirmed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[Project] = relationship("Project")
    confirmed_by: Mapped[User | None] = relationship("User")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<QaBuildingControl project={self.project_id} detected={self.scan_detected}>"
