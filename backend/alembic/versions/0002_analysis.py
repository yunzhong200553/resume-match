"""Add analyses and suggestions tables.

Revision ID: 0002_analysis
Revises: 0001_init
Create Date: 2026-09-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_analysis"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analyses",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("resume_version_id", sa.String(length=64), nullable=False),
        sa.Column("jd_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=True),
        sa.Column("score_level", sa.String(length=20), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("score_breakdown", sa.JSON(), nullable=False),
        sa.Column("item_matches", sa.JSON(), nullable=False),
        sa.Column("missing_requirements", sa.JSON(), nullable=False),
        sa.Column("provider_states", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["resume_version_id"], ["resume_versions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_analyses_resume_version_id", "analyses", ["resume_version_id"])

    op.create_table(
        "suggestions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("analysis_id", sa.String(length=64), nullable=False),
        sa.Column("section_id", sa.String(length=64), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("target_field", sa.String(length=30), nullable=False),
        sa.Column("original", sa.Text(), nullable=False),
        sa.Column("suggested", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("edited_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "analysis_id",
            "section_id",
            "item_id",
            "target_field",
            name="uq_suggestion_target",
        ),
    )
    op.create_index("ix_suggestions_analysis_id", "suggestions", ["analysis_id"])


def downgrade() -> None:
    op.drop_index("ix_suggestions_analysis_id", table_name="suggestions")
    op.drop_table("suggestions")
    op.drop_index("ix_analyses_resume_version_id", table_name="analyses")
    op.drop_table("analyses")