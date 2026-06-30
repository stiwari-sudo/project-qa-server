"""buildings

Revision ID: 0003_buildings
Revises: 0002_project_members
Create Date: 2026-06-18

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_buildings"
down_revision: str | None = "0002_project_members"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS_DEFAULT = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "buildings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_building_project"
        ),
        sa.UniqueConstraint("project_id", "name", name="uq_building_project_name"),
    )
    op.create_index("ix_building_project", "buildings", ["project_id"])

    # Give every existing project one default building so single-building
    # projects are unchanged, and per-building QA can backfill onto it later.
    op.execute(
        sa.text(
            'INSERT INTO buildings (id, project_id, name, "order", created_at, updated_at) '
            "SELECT gen_random_uuid(), p.id, 'Main building', 0, now(), now() FROM projects p"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_building_project", table_name="buildings")
    op.drop_table("buildings")
