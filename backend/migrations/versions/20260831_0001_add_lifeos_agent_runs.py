"""add I19 constrained LifeOS Agent Runtime audit table

Revision ID: 20260831_0001
Revises: 20260830_0002
Create Date: 2026-08-31

The table contains only user-owned declarative plans, read-only tool traces,
verified output, limits and run diagnostics. It stores no executable code and
creates no workspace mutation path; actions remain separate I9 proposals.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260831_0001"
down_revision = "20260830_0002"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _indexes(bind, table: str) -> set[str]:
    return {str(item.get("name")) for item in sa.inspect(bind).get_indexes(table) if item.get("name")}


def upgrade():
    bind = op.get_bind()
    if "lifeos_agent_runs" not in _tables(bind):
        op.create_table(
            "lifeos_agent_runs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("goal", sa.UnicodeText(), nullable=False),
            sa.Column("scope_type", sa.Unicode(length=40), nullable=False, server_default="workspace"),
            sa.Column("scope_id", sa.Integer(), nullable=True),
            sa.Column("scope_label", sa.Unicode(length=255), nullable=False, server_default="All LifeOS"),
            sa.Column("status", sa.Unicode(length=24), nullable=False, server_default="running"),
            sa.Column("plan_json", sa.UnicodeText(), nullable=False, server_default="{}"),
            sa.Column("trace_json", sa.UnicodeText(), nullable=False, server_default="[]"),
            sa.Column("output_json", sa.UnicodeText(), nullable=False, server_default="{}"),
            sa.Column("limits_json", sa.UnicodeText(), nullable=False, server_default="{}"),
            sa.Column("provider", sa.Unicode(length=40), nullable=True),
            sa.Column("model", sa.Unicode(length=120), nullable=True),
            sa.Column("provider_calls", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("tool_calls", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failure_message", sa.UnicodeText(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["user_id"], ["users.id"], ondelete="NO ACTION", name="fk_lifeos_agent_runs_user_id"
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    existing = _indexes(bind, "lifeos_agent_runs")
    for name, columns in (
        ("ix_lifeos_agent_runs_user_id", ["user_id"]),
        ("ix_lifeos_agent_runs_scope_type", ["scope_type"]),
        ("ix_lifeos_agent_runs_scope_id", ["scope_id"]),
        ("ix_lifeos_agent_runs_status", ["status"]),
        ("ix_lifeos_agent_runs_started_at", ["started_at"]),
    ):
        if name not in existing:
            op.create_index(name, "lifeos_agent_runs", columns, unique=False)


def downgrade():
    bind = op.get_bind()
    if "lifeos_agent_runs" not in _tables(bind):
        return
    existing = _indexes(bind, "lifeos_agent_runs")
    for name in (
        "ix_lifeos_agent_runs_started_at",
        "ix_lifeos_agent_runs_status",
        "ix_lifeos_agent_runs_scope_id",
        "ix_lifeos_agent_runs_scope_type",
        "ix_lifeos_agent_runs_user_id",
    ):
        if name in existing:
            op.drop_index(name, table_name="lifeos_agent_runs")
    op.drop_table("lifeos_agent_runs")
