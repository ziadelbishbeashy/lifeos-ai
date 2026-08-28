"""add document collections

Revision ID: 20260828_0002
Revises: 20260828_0001
Create Date: 2026-08-28
"""
from alembic import op
import sqlalchemy as sa
revision = "20260828_0002"
down_revision = "20260828_0001"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "document_collections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Unicode(length=150), nullable=False),
        sa.Column("description", sa.UnicodeText(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="NO ACTION"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_document_collections_user_id"), "document_collections", ["user_id"], unique=False)

    op.create_table(
        "document_collection_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["document_collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collection_id", "document_id", name="uq_document_collection_item"),
    )
    op.create_index(op.f("ix_document_collection_items_collection_id"), "document_collection_items", ["collection_id"], unique=False)
    op.create_index(op.f("ix_document_collection_items_document_id"), "document_collection_items", ["document_id"], unique=False)

    op.create_table(
        "document_collection_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("question", sa.Unicode(length=2000), nullable=False),
        sa.Column("answer", sa.UnicodeText(), nullable=True),
        sa.Column("sources_json", sa.UnicodeText(), nullable=True),
        sa.Column("provider", sa.Unicode(length=30), nullable=False),
        sa.Column("model", sa.Unicode(length=100), nullable=False),
        sa.Column("status", sa.Unicode(length=20), nullable=False),
        sa.Column("source_fingerprint", sa.Unicode(length=64), nullable=True),
        sa.Column("error_message", sa.UnicodeText(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["document_collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="NO ACTION"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_document_collection_questions_collection_id"), "document_collection_questions", ["collection_id"], unique=False)
    op.create_index(op.f("ix_document_collection_questions_user_id"), "document_collection_questions", ["user_id"], unique=False)
    op.create_index(op.f("ix_document_collection_questions_status"), "document_collection_questions", ["status"], unique=False)

def downgrade():
    op.drop_index(op.f("ix_document_collection_questions_status"), table_name="document_collection_questions")
    op.drop_index(op.f("ix_document_collection_questions_user_id"), table_name="document_collection_questions")
    op.drop_index(op.f("ix_document_collection_questions_collection_id"), table_name="document_collection_questions")
    op.drop_table("document_collection_questions")
    op.drop_index(op.f("ix_document_collection_items_document_id"), table_name="document_collection_items")
    op.drop_index(op.f("ix_document_collection_items_collection_id"), table_name="document_collection_items")
    op.drop_table("document_collection_items")
    op.drop_index(op.f("ix_document_collections_user_id"), table_name="document_collections")
    op.drop_table("document_collections")
