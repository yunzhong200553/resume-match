"""初始表结构：resumes / resume_versions / drafts / export_records

Revision ID: 0001_init
Revises:
Create Date: 2026-09-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resumes",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "resume_versions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("resume_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("resume_id", "version", name="uq_resume_version_number"),
    )
    op.create_index("ix_resume_versions_resume_id", "resume_versions", ["resume_id"])

    op.create_table(
        "drafts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("resume_id", sa.String(length=64), nullable=False),
        sa.Column("base_version_id", sa.String(length=64), nullable=True),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("resume_id", name="uq_drafts_resume_id"),
    )

    op.create_table(
        "export_records",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("resume_version_id", sa.String(length=64), nullable=False),
        sa.Column("template_id", sa.String(length=64), nullable=False),
        sa.Column("format", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["resume_version_id"], ["resume_versions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_export_records_resume_version_id", "export_records", ["resume_version_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_export_records_resume_version_id", table_name="export_records")
    op.drop_table("export_records")
    op.drop_table("drafts")
    op.drop_index("ix_resume_versions_resume_id", table_name="resume_versions")
    op.drop_table("resume_versions")
    op.drop_table("resumes")
