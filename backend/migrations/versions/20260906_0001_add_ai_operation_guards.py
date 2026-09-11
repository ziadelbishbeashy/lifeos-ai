"""add AI operation locks and document type detection cache

Revision ID: 20260906_0001
Revises: 20260905_0001
Create Date: 2026-09-06
"""

from alembic import op
import sqlalchemy as sa


revision = "20260906_0001"
down_revision = "20260905_0001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("type_detection_cache_json", sa.UnicodeText(), nullable=True))
        batch_op.add_column(sa.Column("type_detection_fingerprint", sa.Unicode(length=64), nullable=True))
        batch_op.add_column(sa.Column("type_detection_updated_at", sa.DateTime(), nullable=True))

    op.create_table(
        "ai_operation_locks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lock_key", sa.Unicode(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.Unicode(length=80), nullable=False),
        sa.Column("resource_type", sa.Unicode(length=40), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.Unicode(length=64), nullable=True),
        sa.Column("acquired_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_ai_operation_locks_user_id",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_operation_locks"),
        sa.UniqueConstraint("lock_key", name="uq_ai_operation_locks_lock_key"),
    )
    for column in ("lock_key", "user_id", "operation", "resource_type", "resource_id", "expires_at"):
        op.create_index(f"ix_ai_operation_locks_{column}", "ai_operation_locks", [column], unique=False)


def downgrade():
    for column in reversed(("lock_key", "user_id", "operation", "resource_type", "resource_id", "expires_at")):
        op.drop_index(f"ix_ai_operation_locks_{column}", table_name="ai_operation_locks")
    op.drop_table("ai_operation_locks")

    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_column("type_detection_updated_at")
        batch_op.drop_column("type_detection_fingerprint")
        batch_op.drop_column("type_detection_cache_json")
