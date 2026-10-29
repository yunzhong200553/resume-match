"""Track the Analysis that owns an optimized draft.

Revision ID: 0003_draft_analysis_owner
Revises: 0002_analysis
Create Date: 2026-09-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_draft_analysis_owner"
down_revision: Union[str, None] = "0002_analysis"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("drafts") as batch_op:
        batch_op.add_column(sa.Column("analysis_id", sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            "fk_drafts_analysis_id_analyses",
            "analyses",
            ["analysis_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("drafts") as batch_op:
        batch_op.drop_constraint("fk_drafts_analysis_id_analyses", type_="foreignkey")
        batch_op.drop_column("analysis_id")