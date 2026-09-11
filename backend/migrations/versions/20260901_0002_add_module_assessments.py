"""add I21 module assessments

Revision ID: 20260901_0002
Revises: 20260901_0001
Create Date: 2026-09-01
"""

from alembic import op
import sqlalchemy as sa


revision = "20260901_0002"
down_revision = "20260901_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "module_assessments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Unicode(length=180), nullable=False),
        sa.Column("assessment_type", sa.Unicode(length=32), nullable=False),
        sa.Column("assessment_date", sa.Date(), nullable=True),
        sa.Column("assessment_time", sa.Time(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("due_time", sa.Time(), nullable=True),
        sa.Column("weight_percent", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("status", sa.Unicode(length=24), nullable=False, server_default="Upcoming"),
        sa.Column("topics", sa.UnicodeText(), nullable=True),
        sa.Column("estimated_study_minutes", sa.Integer(), nullable=True),
        sa.Column("notes", sa.UnicodeText(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["learning_modules.id"],
            name="fk_module_assessments_module_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_module_assessments"),
    )
    op.create_index("ix_module_assessments_module_id", "module_assessments", ["module_id"], unique=False)
    op.create_index("ix_module_assessments_assessment_type", "module_assessments", ["assessment_type"], unique=False)
    op.create_index("ix_module_assessments_assessment_date", "module_assessments", ["assessment_date"], unique=False)
    op.create_index("ix_module_assessments_due_date", "module_assessments", ["due_date"], unique=False)
    op.create_index("ix_module_assessments_status", "module_assessments", ["status"], unique=False)


def downgrade():
    op.drop_index("ix_module_assessments_status", table_name="module_assessments")
    op.drop_index("ix_module_assessments_due_date", table_name="module_assessments")
    op.drop_index("ix_module_assessments_assessment_date", table_name="module_assessments")
    op.drop_index("ix_module_assessments_assessment_type", table_name="module_assessments")
    op.drop_index("ix_module_assessments_module_id", table_name="module_assessments")
    op.drop_table("module_assessments")
