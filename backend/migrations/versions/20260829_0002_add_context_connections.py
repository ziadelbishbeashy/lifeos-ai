"""add first-class LifeOS context connections

Revision ID: 20260829_0002
Revises: 20260829_0001
Create Date: 2026-08-29

I13 adds one ownership-bounded edge table.  Resource endpoints are polymorphic,
so only user_id has a database FK.  Runtime ownership checks validate both ends
before any edge is created or returned.  This is intentionally SQL Server safe:
no existing table or column is altered.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260829_0002"
down_revision = "20260829_0001"
branch_labels = None
depends_on = None


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade():
    bind = op.get_bind()
    if "lifeos_context_links" in _table_names(bind):
        return

    op.create_table(
        "lifeos_context_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.Unicode(length=40), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.Unicode(length=40), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("relation_type", sa.Unicode(length=48), nullable=False),
        sa.Column("reason", sa.UnicodeText(), nullable=True),
        sa.Column("provenance_type", sa.Unicode(length=48), nullable=False, server_default="user"),
        sa.Column("provenance_id", sa.Integer(), nullable=True),
        sa.Column("evidence_json", sa.UnicodeText(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="NO ACTION",
            name="fk_lifeos_context_links_user_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "source_type", "source_id", "target_type", "target_id", "relation_type",
            name="uq_lifeos_context_link_edge",
        ),
    )
    op.create_index("ix_lifeos_context_links_user_id", "lifeos_context_links", ["user_id"], unique=False)
    op.create_index("ix_lifeos_context_links_source_type", "lifeos_context_links", ["source_type"], unique=False)
    op.create_index("ix_lifeos_context_links_source_id", "lifeos_context_links", ["source_id"], unique=False)
    op.create_index("ix_lifeos_context_links_target_type", "lifeos_context_links", ["target_type"], unique=False)
    op.create_index("ix_lifeos_context_links_target_id", "lifeos_context_links", ["target_id"], unique=False)
    op.create_index("ix_lifeos_context_links_relation_type", "lifeos_context_links", ["relation_type"], unique=False)
    op.create_index("ix_lifeos_context_links_created_at", "lifeos_context_links", ["created_at"], unique=False)


def downgrade():
    bind = op.get_bind()
    if "lifeos_context_links" not in _table_names(bind):
        return
    op.drop_index("ix_lifeos_context_links_created_at", table_name="lifeos_context_links")
    op.drop_index("ix_lifeos_context_links_relation_type", table_name="lifeos_context_links")
    op.drop_index("ix_lifeos_context_links_target_id", table_name="lifeos_context_links")
    op.drop_index("ix_lifeos_context_links_target_type", table_name="lifeos_context_links")
    op.drop_index("ix_lifeos_context_links_source_id", table_name="lifeos_context_links")
    op.drop_index("ix_lifeos_context_links_source_type", table_name="lifeos_context_links")
    op.drop_index("ix_lifeos_context_links_user_id", table_name="lifeos_context_links")
    op.drop_table("lifeos_context_links")
