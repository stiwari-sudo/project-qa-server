"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-02

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Enum labels are the Python member NAMES (SQLAlchemy default), not the values.
discipline_enum = postgresql.ENUM(
    "STRUCTURES",
    "CIVILS",
    "GEOTECHNICAL",
    "HIGHWAYS",
    "OTHER",
    name="discipline_enum",
    create_type=False,
)

_TS_DEFAULT = sa.text("now()")


def upgrade() -> None:
    discipline_enum.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("azure_oid", sa.String(length=64), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column(
            "roles",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("azure_oid", name="uq_users_azure_oid"),
    )

    op.create_table(
        "stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_stages_name"),
        sa.UniqueConstraint("order", name="uq_stages_order"),
    )

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("number", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sector", sa.String(length=100), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("director_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("manager_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cmap_ref", sa.String(length=64), nullable=True),
        sa.Column("cmap_stage", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["director_id"], ["users.id"], ondelete="SET NULL", name="fk_projects_director"
        ),
        sa.ForeignKeyConstraint(
            ["manager_id"], ["users.id"], ondelete="SET NULL", name="fk_projects_manager"
        ),
        sa.UniqueConstraint("cmap_ref", name="uq_projects_cmap_ref"),
    )
    op.create_index("ix_projects_number", "projects", ["number"])

    op.create_table(
        "qa_form_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("structure", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["stage_id"], ["stages.id"], ondelete="CASCADE", name="fk_form_stage"
        ),
        sa.UniqueConstraint(
            "name", "stage_id", "version", name="uq_form_name_stage_version"
        ),
    )
    op.create_index(
        "ix_form_stage_active_version",
        "qa_form_definitions",
        ["stage_id", "is_active", "version"],
    )

    op.create_table(
        "qa_project_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("form_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "responses",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("completion_percentage", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_questions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("answered_questions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column(
            "reminder_sent_offsets",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("last_updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_response_project"
        ),
        sa.ForeignKeyConstraint(
            ["form_id"],
            ["qa_form_definitions.id"],
            ondelete="CASCADE",
            name="fk_response_form",
        ),
        sa.ForeignKeyConstraint(
            ["stage_id"], ["stages.id"], ondelete="CASCADE", name="fk_response_stage"
        ),
        sa.ForeignKeyConstraint(
            ["last_updated_by_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_response_last_updated_by",
        ),
        sa.UniqueConstraint("project_id", "form_id", name="uq_response_project_form"),
    )
    op.create_index(
        "ix_response_project_stage", "qa_project_responses", ["project_id", "stage_id"]
    )
    op.create_index(
        "ix_response_completion", "qa_project_responses", ["completion_percentage"]
    )

    op.create_table(
        "qa_event_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("cause_reason", sa.Text(), nullable=True),
        sa.Column("action_effect", sa.Text(), nullable=True),
        sa.Column("category_of_impact", sa.String(length=150), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("discipline", discipline_enum, nullable=False),
        sa.Column("logged_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_event_project"
        ),
        sa.ForeignKeyConstraint(
            ["stage_id"], ["stages.id"], ondelete="SET NULL", name="fk_event_stage"
        ),
        sa.ForeignKeyConstraint(
            ["logged_by_id"], ["users.id"], ondelete="SET NULL", name="fk_event_logged_by"
        ),
    )
    op.create_index(
        "ix_event_project_created", "qa_event_logs", ["project_id", "created_at"]
    )
    op.create_index(
        "ix_event_stage_created", "qa_event_logs", ["stage_id", "created_at"]
    )
    op.create_index("ix_event_discipline", "qa_event_logs", ["discipline"])

    op.create_table(
        "qa_high_risk_buildings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_high_risk", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("checked_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TS_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_hrb_project"
        ),
        sa.ForeignKeyConstraint(
            ["stage_id"], ["stages.id"], ondelete="SET NULL", name="fk_hrb_stage"
        ),
        sa.ForeignKeyConstraint(
            ["checked_by_id"], ["users.id"], ondelete="SET NULL", name="fk_hrb_checked_by"
        ),
        sa.UniqueConstraint("project_id", "stage_id", name="uq_hrb_project_stage"),
    )
    op.create_index("ix_hrb_is_high_risk", "qa_high_risk_buildings", ["is_high_risk"])


def downgrade() -> None:
    op.drop_table("qa_high_risk_buildings")
    op.drop_table("qa_event_logs")
    op.drop_table("qa_project_responses")
    op.drop_table("qa_form_definitions")
    op.drop_table("projects")
    op.drop_table("stages")
    op.drop_table("users")
    discipline_enum.drop(op.get_bind(), checkfirst=False)
