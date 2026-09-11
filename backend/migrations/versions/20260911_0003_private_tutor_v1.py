"""add Private Tutor V1 study sessions

Revision ID: 20260911_0003
Revises: 20260911_0002
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260911_0003"
down_revision = "20260911_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "private_tutor_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("lecture_id", sa.Integer(), nullable=True),
        sa.Column("mode", sa.Unicode(length=32), nullable=False),
        sa.Column("difficulty", sa.Unicode(length=24), nullable=False),
        sa.Column("topic", sa.Unicode(length=500), nullable=True),
        sa.Column("request_text", sa.UnicodeText(), nullable=True),
        sa.Column("content_json", sa.UnicodeText(), nullable=False),
        sa.Column("sources_json", sa.UnicodeText(), nullable=False),
        sa.Column("answers_json", sa.UnicodeText(), nullable=True),
        sa.Column("weak_areas_json", sa.UnicodeText(), nullable=True),
        sa.Column("score_correct", sa.Integer(), nullable=True),
        sa.Column("score_total", sa.Integer(), nullable=True),
        sa.Column("status", sa.Unicode(length=24), nullable=False),
        sa.Column("provider", sa.Unicode(length=30), nullable=False),
        sa.Column("model", sa.Unicode(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_private_tutor_sessions_user_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["module_id"], ["learning_modules.id"], name="fk_private_tutor_sessions_module_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lecture_id"], ["lectures.id"], name="fk_private_tutor_sessions_lecture_id", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_private_tutor_sessions"),
    )
    for column in ("user_id", "module_id", "lecture_id", "mode", "status", "created_at"):
        op.create_index(f"ix_private_tutor_sessions_{column}", "private_tutor_sessions", [column], unique=False)


def downgrade():
    for column in reversed(("user_id", "module_id", "lecture_id", "mode", "status", "created_at")):
        op.drop_index(f"ix_private_tutor_sessions_{column}", table_name="private_tutor_sessions")
    op.drop_table("private_tutor_sessions")
