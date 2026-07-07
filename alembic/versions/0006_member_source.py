"""project_members.source (manual | resourcing)

Revision ID: 0006_member_source
Revises: 0005_response_building
Create Date: 2026-07-07

Tags each membership with its origin so the TechandData resourcing sync can
reconcile its own ("resourcing") rows without disturbing manually-granted
access. Existing rows default to "manual".
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_member_source"
down_revision: str | None = "0005_response_building"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_members",
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default="manual",
        ),
    )


def downgrade() -> None:
    op.drop_column("project_members", "source")
