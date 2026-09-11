"""add document OCR processing state

Revision ID: 20260826_0001
Revises: 20260811_0002
Create Date: 2026-08-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260826_0001"
down_revision = "20260811_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "documents",
        sa.Column(
            "ocr_status",
            sa.Unicode(length=24),
            nullable=False,
            server_default=sa.text("'not_needed'"),
        ),
    )
    op.add_column("documents", sa.Column("ocr_provider", sa.Unicode(length=64), nullable=True))
    op.add_column("documents", sa.Column("ocr_started_at", sa.DateTime(), nullable=True))
    op.add_column("documents", sa.Column("ocr_completed_at", sa.DateTime(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("ocr_total_pages", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "documents",
        sa.Column("ocr_pages_requested", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "documents",
        sa.Column("ocr_pages_processed", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "documents",
        sa.Column("ocr_low_confidence_pages", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("documents", sa.Column("ocr_average_confidence", sa.Float(), nullable=True))
    op.add_column("documents", sa.Column("ocr_error", sa.UnicodeText(), nullable=True))
    op.create_index(op.f("ix_documents_ocr_status"), "documents", ["ocr_status"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_documents_ocr_status"), table_name="documents")
    op.drop_column("documents", "ocr_error")
    op.drop_column("documents", "ocr_average_confidence")
    op.drop_column("documents", "ocr_low_confidence_pages")
    op.drop_column("documents", "ocr_pages_processed")
    op.drop_column("documents", "ocr_pages_requested")
    op.drop_column("documents", "ocr_total_pages")
    op.drop_column("documents", "ocr_completed_at")
    op.drop_column("documents", "ocr_started_at")
    op.drop_column("documents", "ocr_provider")
    op.drop_column("documents", "ocr_status")
