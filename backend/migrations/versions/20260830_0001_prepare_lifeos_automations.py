"""prepare I17 constrained automations

Revision ID: 20260830_0001
Revises: 20260829_0004
Create Date: 2026-08-30

This preparation migration adds only new user-owned automation definition and
run-history tables. It does not alter existing workspace resources and is safe
for the current SQL Server transition path.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260830_0001"
down_revision = "20260829_0004"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _indexes(bind, table: str) -> set[str]:
    return {str(item.get("name")) for item in sa.inspect(bind).get_indexes(table) if item.get("name")}


def upgrade():
    bind = op.get_bind()
    tables = _tables(bind)

    if "lifeos_automations" not in tables:
        op.create_table(
            "lifeos_automations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.Unicode(length=160), nullable=False),
            sa.Column("description", sa.UnicodeText(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("trigger_type", sa.Unicode(length=32), nullable=False),
            sa.Column("trigger_config_json", sa.UnicodeText(), nullable=False, server_default="{}"),
            sa.Column("action_type", sa.Unicode(length=48), nullable=False),
            sa.Column("action_config_json", sa.UnicodeText(), nullable=False, server_default="{}"),
            sa.Column("timezone", sa.Unicode(length=80), nullable=False, server_default="UTC"),
            sa.Column("status", sa.Unicode(length=24), nullable=False, server_default="ready"),
            sa.Column("next_run_at", sa.DateTime(), nullable=True),
            sa.Column("last_run_at", sa.DateTime(), nullable=True),
            sa.Column("last_event_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="NO ACTION", name="fk_lifeos_automations_user_id"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "name", name="uq_lifeos_automation_user_name"),
        )

    auto_indexes = _indexes(bind, "lifeos_automations")
    for name, columns in (
        ("ix_lifeos_automations_user_id", ["user_id"]),
        ("ix_lifeos_automations_enabled", ["enabled"]),
        ("ix_lifeos_automations_trigger_type", ["trigger_type"]),
        ("ix_lifeos_automations_action_type", ["action_type"]),
        ("ix_lifeos_automations_status", ["status"]),
        ("ix_lifeos_automations_next_run_at", ["next_run_at"]),
        ("ix_lifeos_automations_created_at", ["created_at"]),
    ):
        if name not in auto_indexes:
            op.create_index(name, "lifeos_automations", columns, unique=False)

    tables = _tables(bind)
    if "lifeos_automation_runs" not in tables:
        op.create_table(
            "lifeos_automation_runs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("automation_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.Unicode(length=24), nullable=False, server_default="prepared"),
            sa.Column("trigger_source", sa.Unicode(length=32), nullable=False, server_default="manual"),
            sa.Column("event_id", sa.Integer(), nullable=True),
            sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("output_json", sa.UnicodeText(), nullable=False, server_default="{}"),
            sa.Column("error_message", sa.UnicodeText(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["automation_id"], ["lifeos_automations.id"], ondelete="CASCADE", name="fk_lifeos_automation_runs_automation_id"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="NO ACTION", name="fk_lifeos_automation_runs_user_id"),
            sa.PrimaryKeyConstraint("id"),
        )

    run_indexes = _indexes(bind, "lifeos_automation_runs")
    for name, columns in (
        ("ix_lifeos_automation_runs_automation_id", ["automation_id"]),
        ("ix_lifeos_automation_runs_user_id", ["user_id"]),
        ("ix_lifeos_automation_runs_status", ["status"]),
        ("ix_lifeos_automation_runs_trigger_source", ["trigger_source"]),
        ("ix_lifeos_automation_runs_started_at", ["started_at"]),
    ):
        if name not in run_indexes:
            op.create_index(name, "lifeos_automation_runs", columns, unique=False)


def downgrade():
    bind = op.get_bind()
    tables = _tables(bind)
    if "lifeos_automation_runs" in tables:
        for name in (
            "ix_lifeos_automation_runs_started_at",
            "ix_lifeos_automation_runs_trigger_source",
            "ix_lifeos_automation_runs_status",
            "ix_lifeos_automation_runs_user_id",
            "ix_lifeos_automation_runs_automation_id",
        ):
            if name in _indexes(bind, "lifeos_automation_runs"):
                op.drop_index(name, table_name="lifeos_automation_runs")
        op.drop_table("lifeos_automation_runs")

    tables = _tables(bind)
    if "lifeos_automations" in tables:
        for name in (
            "ix_lifeos_automations_created_at",
            "ix_lifeos_automations_next_run_at",
            "ix_lifeos_automations_status",
            "ix_lifeos_automations_action_type",
            "ix_lifeos_automations_trigger_type",
            "ix_lifeos_automations_enabled",
            "ix_lifeos_automations_user_id",
        ):
            if name in _indexes(bind, "lifeos_automations"):
                op.drop_index(name, table_name="lifeos_automations")
        op.drop_table("lifeos_automations")
