from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPkMixin
from app.models.user import User


class Project(UUIDPkMixin, TimestampMixin, Base):
    """A standalone-owned project. Minimal in v1 (no CMAP sync yet)."""

    __tablename__ = "projects"

    number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    director_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Forward-compat for Phase 6 CMAP sync — nullable, unused in v1.
    cmap_ref: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, unique=True
    )
    cmap_stage: Mapped[str | None] = mapped_column(String(100), nullable=True)

    director: Mapped[User | None] = relationship("User", foreign_keys=[director_id])
    manager: Mapped[User | None] = relationship("User", foreign_keys=[manager_id])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Project {self.number} {self.name}>"
