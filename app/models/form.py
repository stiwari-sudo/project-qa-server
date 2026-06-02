from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPkMixin
from app.models.stage import Stage


class QaFormDefinition(UUIDPkMixin, TimestampMixin, Base):
    """A versioned, JSON-driven QA form bound to a single stage."""

    __tablename__ = "qa_form_definitions"
    __table_args__ = (
        UniqueConstraint("name", "stage_id", "version", name="uq_form_name_stage_version"),
        Index("ix_form_stage_active_version", "stage_id", "is_active", "version"),
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stages.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    structure: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    stage: Mapped[Stage] = relationship("Stage")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<QaFormDefinition {self.name} v{self.version}>"
