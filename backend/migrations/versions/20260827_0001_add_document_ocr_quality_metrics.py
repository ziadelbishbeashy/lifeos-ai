"""add document OCR quality metrics

Revision ID: 20260827_0001
Revises: 20260826_0002
Create Date: 2026-08-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260827_0001"
down_revision = "20260826_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "documents",
        sa.Column(
            "ocr_total_characters",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "ocr_total_words",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "documents",
        sa.Column("ocr_quality", sa.Unicode(length=16), nullable=True),
    )


def downgrade():
    op.drop_column("documents", "ocr_quality")
    op.drop_column("documents", "ocr_total_words")
    op.drop_column("documents", "ocr_total_characters")
