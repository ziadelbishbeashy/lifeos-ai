"""add AI usage observability ledger

Revision ID: 20260905_0001
Revises: 20260901_0002
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa


revision = "20260905_0001"
down_revision = "20260901_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_usage_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.Unicode(length=64), nullable=False),
        sa.Column("endpoint", sa.Unicode(length=160), nullable=True),
        sa.Column("feature", sa.Unicode(length=80), nullable=False, server_default="unknown"),
        sa.Column("operation", sa.Unicode(length=32), nullable=False, server_default="generation"),
        sa.Column("provider", sa.Unicode(length=40), nullable=False),
        sa.Column("model", sa.Unicode(length=120), nullable=False),
        sa.Column("provider_call_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("prompt_characters", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("thinking_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("input_cost_usd", sa.Numeric(18, 10), nullable=True),
        sa.Column("output_cost_usd", sa.Numeric(18, 10), nullable=True),
        sa.Column("total_cost_usd", sa.Numeric(18, 10), nullable=True),
        sa.Column("pricing_source", sa.Unicode(length=120), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("error_category", sa.Unicode(length=80), nullable=True),
        sa.Column("langsmith_run_id", sa.Unicode(length=80), nullable=True),
        sa.Column("usage_json", sa.UnicodeText(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_ai_usage_events_user_id",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_usage_events"),
    )
    for column in (
        "user_id", "request_id", "endpoint", "feature", "operation", "provider",
        "model", "total_cost_usd", "success", "langsmith_run_id", "created_at",
    ):
        op.create_index(f"ix_ai_usage_events_{column}", "ai_usage_events", [column], unique=False)


def downgrade():
    for column in reversed((
        "user_id", "request_id", "endpoint", "feature", "operation", "provider",
        "model", "total_cost_usd", "success", "langsmith_run_id", "created_at",
    )):
        op.drop_index(f"ix_ai_usage_events_{column}", table_name="ai_usage_events")
    op.drop_table("ai_usage_events")
