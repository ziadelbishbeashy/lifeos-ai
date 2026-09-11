"""add task tags for document task conversion

Revision ID: 20260810_0001
Revises: 58aac0d5809f
Create Date: 2026-08-10 16:22:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260810_0001"
down_revision = "58aac0d5809f"
branch_labels = None
depends_on = None


def upgrade():
    """Add optional tags to real tasks and document suggestions."""

    op.add_column(
        "tasks",
        sa.Column(
            "tags",
            sa.Unicode(length=500),
            nullable=True,
        ),
    )

    op.add_column(
        "document_task_suggestions",
        sa.Column(
            "tags",
            sa.Unicode(length=500),
            nullable=True,
        ),
    )


def downgrade():
    """Remove Step 9 tag columns."""

    op.drop_column(
        "document_task_suggestions",
        "tags",
    )

    op.drop_column(
        "tasks",
        "tags",
    )
