"""add I16 structured memory

Revision ID: 20260829_0004
Revises: 20260829_0003
Create Date: 2026-08-29

Only a new user-owned table is introduced. No legacy workspace column is
altered, keeping this SQL Server migration low-risk and reversible.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260829_0004"
down_revision = "20260829_0003"
branch_labels = None
depends_on = None


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade():
    bind = op.get_bind()
    if "lifeos_memories" in _table_names(bind):
        return
    op.create_table(
        "lifeos_memories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("memory_type", sa.Unicode(length=40), nullable=False),
        sa.Column("memory_key", sa.Unicode(length=160), nullable=False),
        sa.Column("label", sa.Unicode(length=180), nullable=False),
        sa.Column("value_json", sa.UnicodeText(), nullable=False, server_default="{}"),
        sa.Column("scope_type", sa.Unicode(length=40), nullable=True),
        sa.Column("scope_id", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.Unicode(length=48), nullable=False, server_default="user_confirmed"),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("user_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.Unicode(length=24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="NO ACTION", name="fk_lifeos_memories_user_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "memory_type", "memory_key", name="uq_lifeos_memory_key"),
    )
    for name, columns in (
        ("ix_lifeos_memories_user_id", ["user_id"]),
        ("ix_lifeos_memories_memory_type", ["memory_type"]),
        ("ix_lifeos_memories_memory_key", ["memory_key"]),
        ("ix_lifeos_memories_scope_type", ["scope_type"]),
        ("ix_lifeos_memories_scope_id", ["scope_id"]),
        ("ix_lifeos_memories_source_type", ["source_type"]),
        ("ix_lifeos_memories_status", ["status"]),
        ("ix_lifeos_memories_created_at", ["created_at"]),
        ("ix_lifeos_memories_expires_at", ["expires_at"]),
    ):
        op.create_index(name, "lifeos_memories", columns, unique=False)


def downgrade():
    bind = op.get_bind()
    if "lifeos_memories" not in _table_names(bind):
        return
    for name in (
        "ix_lifeos_memories_expires_at",
        "ix_lifeos_memories_created_at",
        "ix_lifeos_memories_status",
        "ix_lifeos_memories_source_type",
        "ix_lifeos_memories_scope_id",
        "ix_lifeos_memories_scope_type",
        "ix_lifeos_memories_memory_key",
        "ix_lifeos_memories_memory_type",
        "ix_lifeos_memories_user_id",
    ):
        op.drop_index(name, table_name="lifeos_memories")
    op.drop_table("lifeos_memories")
