"""add structured document tables

Revision ID: 20260828_0001
Revises: 20260827_0001
Create Date: 2026-08-28
"""
from alembic import op
import sqlalchemy as sa
revision = "20260828_0001"
down_revision = "20260827_0001"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "document_tables",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("table_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.Unicode(length=255), nullable=True),
        sa.Column("headers_json", sa.UnicodeText(), nullable=True),
        sa.Column("rows_json", sa.UnicodeText(), nullable=False),
        sa.Column("markdown_text", sa.UnicodeText(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("column_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("source_fingerprint", sa.Unicode(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="NO ACTION"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "page_number", "table_index", name="uq_document_table_page_index"),
    )
    op.create_index(op.f("ix_document_tables_document_id"), "document_tables", ["document_id"], unique=False)
    op.create_index(op.f("ix_document_tables_user_id"), "document_tables", ["user_id"], unique=False)
    op.create_index(op.f("ix_document_tables_page_number"), "document_tables", ["page_number"], unique=False)
    op.create_index(op.f("ix_document_tables_source_fingerprint"), "document_tables", ["source_fingerprint"], unique=False)

    op.add_column("document_chunks", sa.Column("content_type", sa.Unicode(length=20), nullable=False, server_default="text"))
    op.add_column("document_chunks", sa.Column("table_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_document_chunks_table_id", "document_chunks", "document_tables", ["table_id"], ["id"], ondelete="NO ACTION")
    op.create_index(op.f("ix_document_chunks_content_type"), "document_chunks", ["content_type"], unique=False)
    op.create_index(op.f("ix_document_chunks_table_id"), "document_chunks", ["table_id"], unique=False)

def downgrade():
    op.drop_index(op.f("ix_document_chunks_table_id"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_content_type"), table_name="document_chunks")
    op.drop_constraint("fk_document_chunks_table_id", "document_chunks", type_="foreignkey")
    op.drop_column("document_chunks", "table_id")
    op.drop_column("document_chunks", "content_type")
    op.drop_index(op.f("ix_document_tables_source_fingerprint"), table_name="document_tables")
    op.drop_index(op.f("ix_document_tables_page_number"), table_name="document_tables")
    op.drop_index(op.f("ix_document_tables_user_id"), table_name="document_tables")
    op.drop_index(op.f("ix_document_tables_document_id"), table_name="document_tables")
    op.drop_table("document_tables")
