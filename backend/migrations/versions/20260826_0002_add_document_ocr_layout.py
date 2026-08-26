"""add document OCR word layout

Revision ID: 20260826_0002
Revises: 20260826_0001
Create Date: 2026-08-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260826_0002"
down_revision = "20260826_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "documents",
        sa.Column("ocr_layout_json", sa.UnicodeText(), nullable=True),
    )


def downgrade():
    op.drop_column("documents", "ocr_layout_json")
