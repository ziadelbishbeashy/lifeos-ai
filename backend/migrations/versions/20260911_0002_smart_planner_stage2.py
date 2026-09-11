"""Smart Planner V1 Stage 2 commitments and rebalance metadata

Revision ID: 20260911_0002
Revises: 20260911_0001
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260911_0002"
down_revision = "20260911_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("smart_planner_plans", sa.Column("project_id", sa.Integer(), nullable=True))
    op.add_column("smart_planner_plans", sa.Column("supersedes_plan_id", sa.Integer(), nullable=True))
    op.create_index("ix_smart_planner_plans_project_id", "smart_planner_plans", ["project_id"], unique=False)
    op.create_index("ix_smart_planner_plans_supersedes_plan_id", "smart_planner_plans", ["supersedes_plan_id"], unique=False)

    op.create_table(
        "smart_planner_commitments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Unicode(length=255), nullable=False),
        sa.Column("commitment_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("commitment_type", sa.Unicode(length=32), nullable=False),
        sa.Column("notes", sa.UnicodeText(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_smart_planner_commitments_user_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_smart_planner_commitments"),
    )
    op.create_index("ix_smart_planner_commitments_user_id", "smart_planner_commitments", ["user_id"], unique=False)
    op.create_index("ix_smart_planner_commitments_commitment_date", "smart_planner_commitments", ["commitment_date"], unique=False)
    op.create_index("ix_smart_planner_commitments_commitment_type", "smart_planner_commitments", ["commitment_type"], unique=False)


def downgrade():
    op.drop_index("ix_smart_planner_commitments_commitment_type", table_name="smart_planner_commitments")
    op.drop_index("ix_smart_planner_commitments_commitment_date", table_name="smart_planner_commitments")
    op.drop_index("ix_smart_planner_commitments_user_id", table_name="smart_planner_commitments")
    op.drop_table("smart_planner_commitments")
    op.drop_index("ix_smart_planner_plans_supersedes_plan_id", table_name="smart_planner_plans")
    op.drop_index("ix_smart_planner_plans_project_id", table_name="smart_planner_plans")
    op.drop_column("smart_planner_plans", "supersedes_plan_id")
    op.drop_column("smart_planner_plans", "project_id")
