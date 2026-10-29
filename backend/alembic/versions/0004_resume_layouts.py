"""Persist named job layouts independently from the base resume."""

from alembic import op
import sqlalchemy as sa

revision = "0004_resume_layouts"
down_revision = "0003_draft_analysis_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resume_layouts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("resume_id", sa.String(64), sa.ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("jd_text", sa.Text(), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("analysis_id", sa.String(64), sa.ForeignKey("analyses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("resume_id", "name", name="uq_resume_layout_name"),
    )
    op.create_index("ix_resume_layouts_resume_id", "resume_layouts", ["resume_id"])
    with op.batch_alter_table("export_records") as batch:
        batch.add_column(sa.Column("layout_id", sa.String(64), nullable=True))
        batch.create_foreign_key("fk_export_records_layout_id", "resume_layouts", ["layout_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("export_records") as batch:
        batch.drop_constraint("fk_export_records_layout_id", type_="foreignkey")
        batch.drop_column("layout_id")
    op.drop_index("ix_resume_layouts_resume_id", table_name="resume_layouts")
    op.drop_table("resume_layouts")
