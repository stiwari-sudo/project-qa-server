"""per-building QA: building_id on responses + HRB

Revision ID: 0005_response_building
Revises: 0004_building_control
Create Date: 2026-06-30

Scopes QA to a building instead of directly to a project. Every project already
has exactly one "Main building" (seeded in 0003), so this backfills each existing
response / HRB row onto its project's primary building and is invisible to
single-building projects. The unique keys move from (project, *) to (building, *).
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_response_building"
down_revision: str | None = "0004_building_control"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Primary building of a project = lowest "order", then oldest. Used to backfill.
_PRIMARY_BUILDING = (
    'SELECT b.id FROM buildings b WHERE b.project_id = {table}.project_id '
    'ORDER BY b."order", b.created_at LIMIT 1'
)


def upgrade() -> None:
    # Defensive: ensure every project has a building before we make the column
    # NOT NULL (0003 already seeds one; this covers any created since).
    op.execute(
        sa.text(
            'INSERT INTO buildings (id, project_id, name, "order", created_at, updated_at) '
            "SELECT gen_random_uuid(), p.id, 'Main building', 0, now(), now() "
            "FROM projects p "
            "WHERE NOT EXISTS (SELECT 1 FROM buildings b WHERE b.project_id = p.id)"
        )
    )

    # --- qa_project_responses -------------------------------------------------
    op.add_column(
        "qa_project_responses",
        sa.Column("building_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE qa_project_responses SET building_id = ("
            + _PRIMARY_BUILDING.format(table="qa_project_responses")
            + ")"
        )
    )
    op.alter_column("qa_project_responses", "building_id", nullable=False)
    op.create_foreign_key(
        "fk_response_building",
        "qa_project_responses",
        "buildings",
        ["building_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "uq_response_project_form", "qa_project_responses", type_="unique"
    )
    op.create_unique_constraint(
        "uq_response_building_form", "qa_project_responses", ["building_id", "form_id"]
    )
    op.create_index(
        "ix_response_building_stage",
        "qa_project_responses",
        ["building_id", "stage_id"],
    )

    # --- qa_high_risk_buildings ----------------------------------------------
    op.add_column(
        "qa_high_risk_buildings",
        sa.Column("building_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE qa_high_risk_buildings SET building_id = ("
            + _PRIMARY_BUILDING.format(table="qa_high_risk_buildings")
            + ")"
        )
    )
    op.alter_column("qa_high_risk_buildings", "building_id", nullable=False)
    op.create_foreign_key(
        "fk_hrb_building",
        "qa_high_risk_buildings",
        "buildings",
        ["building_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "uq_hrb_project_stage", "qa_high_risk_buildings", type_="unique"
    )
    op.create_unique_constraint(
        "uq_hrb_building_stage", "qa_high_risk_buildings", ["building_id", "stage_id"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_hrb_building_stage", "qa_high_risk_buildings", type_="unique"
    )
    op.create_unique_constraint(
        "uq_hrb_project_stage", "qa_high_risk_buildings", ["project_id", "stage_id"]
    )
    op.drop_constraint("fk_hrb_building", "qa_high_risk_buildings", type_="foreignkey")
    op.drop_column("qa_high_risk_buildings", "building_id")

    op.drop_index("ix_response_building_stage", table_name="qa_project_responses")
    op.drop_constraint(
        "uq_response_building_form", "qa_project_responses", type_="unique"
    )
    op.create_unique_constraint(
        "uq_response_project_form", "qa_project_responses", ["project_id", "form_id"]
    )
    op.drop_constraint("fk_response_building", "qa_project_responses", type_="foreignkey")
    op.drop_column("qa_project_responses", "building_id")
