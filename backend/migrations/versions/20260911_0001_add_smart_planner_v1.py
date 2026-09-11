"""add Smart Planner V1 accepted plans and blocks

Revision ID: 20260911_0001
Revises: 20260906_0001
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260911_0001"
down_revision = "20260906_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "smart_planner_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Unicode(length=255), nullable=False),
        sa.Column("mode", sa.Unicode(length=24), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Unicode(length=24), nullable=False),
        sa.Column("request_text", sa.UnicodeText(), nullable=True),
        sa.Column("summary", sa.UnicodeText(), nullable=True),
        sa.Column("working_start", sa.Time(), nullable=False),
        sa.Column("working_end", sa.Time(), nullable=False),
        sa.Column("break_minutes", sa.Integer(), nullable=False),
        sa.Column("available_minutes", sa.Integer(), nullable=False),
        sa.Column("scheduled_minutes", sa.Integer(), nullable=False),
        sa.Column("overload_minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("accepted_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_smart_planner_plans_user_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_smart_planner_plans"),
    )
    for column in ("user_id", "mode", "start_date", "end_date", "status", "created_at"):
        op.create_index(f"ix_smart_planner_plans_{column}", "smart_planner_plans", [column], unique=False)

    op.create_table(
        "smart_planner_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("block_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("title", sa.Unicode(length=255), nullable=False),
        sa.Column("block_type", sa.Unicode(length=24), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("project_title", sa.Unicode(length=255), nullable=True),
        sa.Column("importance", sa.Unicode(length=24), nullable=True),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("rationale", sa.UnicodeText(), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(["plan_id"], ["smart_planner_plans.id"], name="fk_smart_planner_blocks_plan_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name="fk_smart_planner_blocks_task_id", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_smart_planner_blocks"),
    )
    for column in ("plan_id", "task_id", "block_date", "project_id"):
        op.create_index(f"ix_smart_planner_blocks_{column}", "smart_planner_blocks", [column], unique=False)


def downgrade():
    for column in reversed(("plan_id", "task_id", "block_date", "project_id")):
        op.drop_index(f"ix_smart_planner_blocks_{column}", table_name="smart_planner_blocks")
    op.drop_table("smart_planner_blocks")
    for column in reversed(("user_id", "mode", "start_date", "end_date", "status", "created_at")):
        op.drop_index(f"ix_smart_planner_plans_{column}", table_name="smart_planner_plans")
    op.drop_table("smart_planner_plans")
