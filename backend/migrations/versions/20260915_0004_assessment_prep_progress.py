"""Track assessment preparation progress in Smart Planner.

Revision ID: 20260915_0004
Revises: 20260912_0003
"""
from alembic import op
import sqlalchemy as sa

revision = "20260915_0004"
down_revision = "20260912_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "smart_planner_blocks",
        sa.Column("assessment_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "smart_planner_blocks",
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_smart_planner_blocks_assessment_id",
        "smart_planner_blocks",
        ["assessment_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_smart_planner_blocks_assessment_id",
        "smart_planner_blocks",
        "module_assessments",
        ["assessment_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint(
        "fk_smart_planner_blocks_assessment_id",
        "smart_planner_blocks",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_smart_planner_blocks_assessment_id",
        table_name="smart_planner_blocks",
    )
    op.drop_column("smart_planner_blocks", "completed_at")
    op.drop_column("smart_planner_blocks", "assessment_id")
