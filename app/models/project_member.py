from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPkMixin
from app.models.project import Project
from app.models.user import User


class ProjectMember(UUIDPkMixin, TimestampMixin, Base):
    """A user granted visibility of a project. Drives the "my projects" scope
    for engineers; view-all roles ignore membership. Assignment is manual for
    now and will later be fed from SharePoint."""

    __tablename__ = "project_members"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    project: Mapped[Project] = relationship("Project", foreign_keys=[project_id])
    user: Mapped[User] = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_member"),
        Index("ix_project_member_user", "user_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ProjectMember project={self.project_id} user={self.user_id}>"
