"""add I14 event engine and I15 proactive in-app notifications

Revision ID: 20260829_0003
Revises: 20260829_0002
Create Date: 2026-08-29

Only new tables are introduced. Existing project/task/document columns are not
altered, keeping the migration safe for the legacy Microsoft SQL Server schema.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260829_0003"
down_revision = "20260829_0002"
branch_labels = None
depends_on = None


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade():
    bind = op.get_bind()
    existing = _table_names(bind)

    if "lifeos_intelligence_events" not in existing:
        op.create_table(
            "lifeos_intelligence_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.Unicode(length=80), nullable=False),
            sa.Column("severity", sa.Unicode(length=24), nullable=False, server_default="normal"),
            sa.Column("lifecycle", sa.Unicode(length=24), nullable=False, server_default="open"),
            sa.Column("object_type", sa.Unicode(length=64), nullable=False),
            sa.Column("object_id", sa.Integer(), nullable=True),
            sa.Column("project_id", sa.Integer(), nullable=True),
            sa.Column("title", sa.Unicode(length=255), nullable=False),
            sa.Column("summary", sa.UnicodeText(), nullable=True),
            sa.Column("dedupe_key", sa.Unicode(length=255), nullable=False),
            sa.Column("context_json", sa.UnicodeText(), nullable=False, server_default="{}"),
            sa.Column("source_type", sa.Unicode(length=64), nullable=False, server_default="state_scan"),
            sa.Column("source_id", sa.Integer(), nullable=True),
            sa.Column("detected_at", sa.DateTime(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), nullable=False),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["user_id"], ["users.id"], ondelete="NO ACTION",
                name="fk_lifeos_intelligence_events_user_id",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "user_id", "dedupe_key",
                name="uq_lifeos_intelligence_event_dedupe",
            ),
        )
        op.create_index("ix_lifeos_intelligence_events_user_id", "lifeos_intelligence_events", ["user_id"], unique=False)
        op.create_index("ix_lifeos_intelligence_events_event_type", "lifeos_intelligence_events", ["event_type"], unique=False)
        op.create_index("ix_lifeos_intelligence_events_severity", "lifeos_intelligence_events", ["severity"], unique=False)
        op.create_index("ix_lifeos_intelligence_events_lifecycle", "lifeos_intelligence_events", ["lifecycle"], unique=False)
        op.create_index("ix_lifeos_intelligence_events_object_type", "lifeos_intelligence_events", ["object_type"], unique=False)
        op.create_index("ix_lifeos_intelligence_events_project_id", "lifeos_intelligence_events", ["project_id"], unique=False)
        op.create_index("ix_lifeos_intelligence_events_detected_at", "lifeos_intelligence_events", ["detected_at"], unique=False)

    existing = _table_names(bind)
    if "lifeos_proactive_notifications" not in existing:
        op.create_table(
            "lifeos_proactive_notifications",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("event_id", sa.Integer(), nullable=False),
            sa.Column("category", sa.Unicode(length=64), nullable=False, server_default="attention"),
            sa.Column("severity", sa.Unicode(length=24), nullable=False, server_default="normal"),
            sa.Column("status", sa.Unicode(length=24), nullable=False, server_default="unread"),
            sa.Column("title", sa.Unicode(length=255), nullable=False),
            sa.Column("message", sa.UnicodeText(), nullable=False),
            sa.Column("action_label", sa.Unicode(length=80), nullable=True),
            sa.Column("action_href", sa.Unicode(length=500), nullable=True),
            sa.Column("ask_query", sa.Unicode(length=1000), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("read_at", sa.DateTime(), nullable=True),
            sa.Column("dismissed_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["user_id"], ["users.id"], ondelete="NO ACTION",
                name="fk_lifeos_proactive_notifications_user_id",
            ),
            sa.ForeignKeyConstraint(
                ["event_id"], ["lifeos_intelligence_events.id"], ondelete="CASCADE",
                name="fk_lifeos_proactive_notifications_event_id",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "user_id", "event_id",
                name="uq_lifeos_proactive_notification_event",
            ),
        )
        op.create_index("ix_lifeos_proactive_notifications_user_id", "lifeos_proactive_notifications", ["user_id"], unique=False)
        op.create_index("ix_lifeos_proactive_notifications_event_id", "lifeos_proactive_notifications", ["event_id"], unique=False)
        op.create_index("ix_lifeos_proactive_notifications_category", "lifeos_proactive_notifications", ["category"], unique=False)
        op.create_index("ix_lifeos_proactive_notifications_severity", "lifeos_proactive_notifications", ["severity"], unique=False)
        op.create_index("ix_lifeos_proactive_notifications_status", "lifeos_proactive_notifications", ["status"], unique=False)
        op.create_index("ix_lifeos_proactive_notifications_created_at", "lifeos_proactive_notifications", ["created_at"], unique=False)


def downgrade():
    bind = op.get_bind()
    existing = _table_names(bind)

    if "lifeos_proactive_notifications" in existing:
        op.drop_index("ix_lifeos_proactive_notifications_created_at", table_name="lifeos_proactive_notifications")
        op.drop_index("ix_lifeos_proactive_notifications_status", table_name="lifeos_proactive_notifications")
        op.drop_index("ix_lifeos_proactive_notifications_severity", table_name="lifeos_proactive_notifications")
        op.drop_index("ix_lifeos_proactive_notifications_category", table_name="lifeos_proactive_notifications")
        op.drop_index("ix_lifeos_proactive_notifications_event_id", table_name="lifeos_proactive_notifications")
        op.drop_index("ix_lifeos_proactive_notifications_user_id", table_name="lifeos_proactive_notifications")
        op.drop_table("lifeos_proactive_notifications")

    existing = _table_names(bind)
    if "lifeos_intelligence_events" in existing:
        op.drop_index("ix_lifeos_intelligence_events_detected_at", table_name="lifeos_intelligence_events")
        op.drop_index("ix_lifeos_intelligence_events_project_id", table_name="lifeos_intelligence_events")
        op.drop_index("ix_lifeos_intelligence_events_object_type", table_name="lifeos_intelligence_events")
        op.drop_index("ix_lifeos_intelligence_events_lifecycle", table_name="lifeos_intelligence_events")
        op.drop_index("ix_lifeos_intelligence_events_severity", table_name="lifeos_intelligence_events")
        op.drop_index("ix_lifeos_intelligence_events_event_type", table_name="lifeos_intelligence_events")
        op.drop_index("ix_lifeos_intelligence_events_user_id", table_name="lifeos_intelligence_events")
        op.drop_table("lifeos_intelligence_events")
