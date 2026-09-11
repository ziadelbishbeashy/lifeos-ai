"""add LifeOS intelligence action proposals and activity history

Revision ID: 20260829_0001
Revises: 20260828_0004
Create Date: 2026-08-29

I9/I10 add only new tables.  No existing project/document/task column is
altered, which keeps the migration safe on Microsoft SQL Server.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260829_0001"
down_revision = "20260828_0004"
branch_labels = None
depends_on = None


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade():
    bind = op.get_bind()
    existing = _table_names(bind)

    if "lifeos_action_proposals" not in existing:
        op.create_table(
            "lifeos_action_proposals",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("action_type", sa.Unicode(length=64), nullable=False),
            sa.Column("status", sa.Unicode(length=24), nullable=False, server_default="pending"),
            sa.Column("title", sa.Unicode(length=255), nullable=False),
            sa.Column("reason", sa.UnicodeText(), nullable=True),
            sa.Column("target_type", sa.Unicode(length=64), nullable=False),
            sa.Column("target_id", sa.Integer(), nullable=True),
            sa.Column("project_id", sa.Integer(), nullable=True),
            sa.Column("payload_json", sa.UnicodeText(), nullable=False, server_default="{}"),
            sa.Column("evidence_json", sa.UnicodeText(), nullable=False, server_default="[]"),
            sa.Column("risk_level", sa.Unicode(length=24), nullable=False, server_default="medium"),
            sa.Column("requires_confirmation", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("execution_resource_type", sa.Unicode(length=64), nullable=True),
            sa.Column("execution_resource_id", sa.Integer(), nullable=True),
            sa.Column("failure_message", sa.UnicodeText(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="NO ACTION", name="fk_lifeos_action_proposals_user_id"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_lifeos_action_proposals_user_id", "lifeos_action_proposals", ["user_id"], unique=False)
        op.create_index("ix_lifeos_action_proposals_action_type", "lifeos_action_proposals", ["action_type"], unique=False)
        op.create_index("ix_lifeos_action_proposals_status", "lifeos_action_proposals", ["status"], unique=False)
        op.create_index("ix_lifeos_action_proposals_project_id", "lifeos_action_proposals", ["project_id"], unique=False)
        op.create_index("ix_lifeos_action_proposals_created_at", "lifeos_action_proposals", ["created_at"], unique=False)

    existing = _table_names(bind)
    if "lifeos_activity_events" not in existing:
        op.create_table(
            "lifeos_activity_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.Unicode(length=80), nullable=False),
            sa.Column("object_type", sa.Unicode(length=64), nullable=False),
            sa.Column("object_id", sa.Integer(), nullable=True),
            sa.Column("project_id", sa.Integer(), nullable=True),
            sa.Column("title", sa.Unicode(length=255), nullable=False),
            sa.Column("summary", sa.UnicodeText(), nullable=True),
            sa.Column("changes_json", sa.UnicodeText(), nullable=False, server_default="{}"),
            sa.Column("source_type", sa.Unicode(length=64), nullable=False, server_default="user"),
            sa.Column("source_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="NO ACTION", name="fk_lifeos_activity_events_user_id"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_lifeos_activity_events_user_id", "lifeos_activity_events", ["user_id"], unique=False)
        op.create_index("ix_lifeos_activity_events_event_type", "lifeos_activity_events", ["event_type"], unique=False)
        op.create_index("ix_lifeos_activity_events_object_type", "lifeos_activity_events", ["object_type"], unique=False)
        op.create_index("ix_lifeos_activity_events_project_id", "lifeos_activity_events", ["project_id"], unique=False)
        op.create_index("ix_lifeos_activity_events_created_at", "lifeos_activity_events", ["created_at"], unique=False)


def downgrade():
    bind = op.get_bind()
    existing = _table_names(bind)

    if "lifeos_activity_events" in existing:
        op.drop_index("ix_lifeos_activity_events_created_at", table_name="lifeos_activity_events")
        op.drop_index("ix_lifeos_activity_events_project_id", table_name="lifeos_activity_events")
        op.drop_index("ix_lifeos_activity_events_object_type", table_name="lifeos_activity_events")
        op.drop_index("ix_lifeos_activity_events_event_type", table_name="lifeos_activity_events")
        op.drop_index("ix_lifeos_activity_events_user_id", table_name="lifeos_activity_events")
        op.drop_table("lifeos_activity_events")

    existing = _table_names(bind)
    if "lifeos_action_proposals" in existing:
        op.drop_index("ix_lifeos_action_proposals_created_at", table_name="lifeos_action_proposals")
        op.drop_index("ix_lifeos_action_proposals_project_id", table_name="lifeos_action_proposals")
        op.drop_index("ix_lifeos_action_proposals_status", table_name="lifeos_action_proposals")
        op.drop_index("ix_lifeos_action_proposals_action_type", table_name="lifeos_action_proposals")
        op.drop_index("ix_lifeos_action_proposals_user_id", table_name="lifeos_action_proposals")
        op.drop_table("lifeos_action_proposals")
