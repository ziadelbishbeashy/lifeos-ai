"""add document chunk embeddings

Revision ID: 58aac0d5809f
Revises: 2c300e7e2116
Create Date: 2026-08-03 17:48:12.745552
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql


revision = '58aac0d5809f'
down_revision = '2c300e7e2116'
branch_labels = None
depends_on = None


def upgrade():
    """Add semantic embedding storage to document chunks."""

    op.add_column(
        "document_chunks",
        sa.Column(
            "embedding_json",
            sa.UnicodeText(),
            nullable=True,
        ),
    )

    op.add_column(
        "document_chunks",
        sa.Column(
            "embedding_provider",
            sa.Unicode(length=30),
            nullable=True,
        ),
    )

    op.add_column(
        "document_chunks",
        sa.Column(
            "embedding_model",
            sa.Unicode(length=100),
            nullable=True,
        ),
    )

    op.add_column(
        "document_chunks",
        sa.Column(
            "embedding_dimensions",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "document_chunks",
        sa.Column(
            "embedding_fingerprint",
            sa.Unicode(length=64),
            nullable=True,
        ),
    )

    op.add_column(
        "document_chunks",
        sa.Column(
            "embedded_at",
            sa.DateTime(),
            nullable=True,
        ),
    )


def downgrade():
    """Remove semantic embedding storage from document chunks."""

    op.drop_column(
        "document_chunks",
        "embedded_at",
    )

    op.drop_column(
        "document_chunks",
        "embedding_fingerprint",
    )

    op.drop_column(
        "document_chunks",
        "embedding_dimensions",
    )

    op.drop_column(
        "document_chunks",
        "embedding_model",
    )

    op.drop_column(
        "document_chunks",
        "embedding_provider",
    )

    op.drop_column(
        "document_chunks",
        "embedding_json",
    )