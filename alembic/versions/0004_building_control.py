"""building control

Revision ID: 0004_building_control
Revises: 0003_buildings
Create Date: 2026-06-25

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_building_control"
down_revision: str | None = "0003_buildings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS_DEFAULT = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "qa_building_control",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scan_detected", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("scan_status", sa.String(length=40), nullable=True),
        sa.Column("scan_detail", sa.Text(), nullable=True),
        sa.Column("scan_path", sa.Text(), nullable=True),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manual_status", sa.String(length=20), nullable=True),
        sa.Column("confirmed_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_building_control_project"
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_id"], ["users.id"], ondelete="SET NULL", name="fk_building_control_confirmed_by"
        ),
        sa.UniqueConstraint("project_id", name="uq_building_control_project"),
    )
    op.create_index("ix_building_control_project", "qa_building_control", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_building_control_project", table_name="qa_building_control")
    op.drop_table("qa_building_control")
