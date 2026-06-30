"""project_members

Revision ID: 0002_project_members
Revises: 0001_initial
Create Date: 2026-06-16

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_project_members"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS_DEFAULT = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "project_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_project_member_project"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name="fk_project_member_user"
        ),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_member"),
    )
    op.create_index("ix_project_member_user", "project_members", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_project_member_user", table_name="project_members")
    op.drop_table("project_members")
