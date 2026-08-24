"""add project questions for multi-document RAG

Revision ID: 20260810_0002
Revises: 20260810_0001
Create Date: 2026-08-10 18:54:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260810_0002"
down_revision = "20260810_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_project_questions_project_id"),
        "project_questions",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_questions_user_id"),
        "project_questions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_questions_status"),
        "project_questions",
        ["status"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_project_questions_status"),
        table_name="project_questions",
    )
    op.drop_index(
        op.f("ix_project_questions_user_id"),
        table_name="project_questions",
    )
    op.drop_index(
        op.f("ix_project_questions_project_id"),
        table_name="project_questions",
    )
    op.drop_table("project_questions")
