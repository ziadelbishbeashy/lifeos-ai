"""Private Tutor V1 Stage 2 conversations and mastery

Revision ID: 20260912_0001
Revises: 20260911_0003
"""
from alembic import op
import sqlalchemy as sa

revision = "20260912_0001"
down_revision = "20260911_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("private_tutor_sessions", sa.Column("conversation_key", sa.Unicode(length=64), nullable=True))
    op.add_column("private_tutor_sessions", sa.Column("parent_session_id", sa.Integer(), nullable=True))
    op.create_index("ix_private_tutor_sessions_conversation_key", "private_tutor_sessions", ["conversation_key"], unique=False)
    op.create_index("ix_private_tutor_sessions_parent_session_id", "private_tutor_sessions", ["parent_session_id"], unique=False)
    op.create_foreign_key("fk_private_tutor_sessions_parent_session_id", "private_tutor_sessions", "private_tutor_sessions", ["parent_session_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "private_tutor_mastery",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("topic_key", sa.Unicode(length=180), nullable=False),
        sa.Column("topic_label", sa.Unicode(length=180), nullable=False),
        sa.Column("quiz_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mastery_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("best_percentage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_percentage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_session_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["module_id"], ["learning_modules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["last_session_id"], ["private_tutor_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "module_id", "topic_key", name="uq_private_tutor_mastery_user_module_topic"),
    )
    for column in ("user_id", "module_id", "mastery_score", "updated_at"):
        op.create_index(f"ix_private_tutor_mastery_{column}", "private_tutor_mastery", [column], unique=False)


def downgrade():
    for column in reversed(("user_id", "module_id", "mastery_score", "updated_at")):
        op.drop_index(f"ix_private_tutor_mastery_{column}", table_name="private_tutor_mastery")
    op.drop_table("private_tutor_mastery")
    op.drop_constraint("fk_private_tutor_sessions_parent_session_id", "private_tutor_sessions", type_="foreignkey")
    op.drop_index("ix_private_tutor_sessions_parent_session_id", table_name="private_tutor_sessions")
    op.drop_index("ix_private_tutor_sessions_conversation_key", table_name="private_tutor_sessions")
    op.drop_column("private_tutor_sessions", "parent_session_id")
    op.drop_column("private_tutor_sessions", "conversation_key")
