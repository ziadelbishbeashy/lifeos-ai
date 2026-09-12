"""V-SPACE personalization life-context profile

Revision ID: 20260912_0002
Revises: 20260912_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "20260912_0002"
down_revision = "20260912_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_personalization_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("onboarding_state", sa.Unicode(length=24), nullable=False, server_default="deferred"),
        sa.Column("usual_wake_time", sa.Time(), nullable=True),
        sa.Column("usual_sleep_time", sa.Time(), nullable=True),
        sa.Column("productive_period", sa.Unicode(length=24), nullable=True),
        sa.Column("preferred_focus_minutes", sa.Integer(), nullable=True),
        sa.Column("preferred_break_minutes", sa.Integer(), nullable=True),
        sa.Column("planning_intensity", sa.Unicode(length=24), nullable=True),
        sa.Column("workday_start", sa.Time(), nullable=True),
        sa.Column("workday_end", sa.Time(), nullable=True),
        sa.Column("avoid_after_time", sa.Time(), nullable=True),
        sa.Column("regular_commitments_json", sa.UnicodeText(), nullable=False, server_default="[]"),
        sa.Column("priorities_json", sa.UnicodeText(), nullable=False, server_default="[]"),
        sa.Column("overload_behavior", sa.Unicode(length=40), nullable=True),
        sa.Column("data_use_notice_version", sa.Unicode(length=16), nullable=True),
        sa.Column("data_use_acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("deferred_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_personalization_profiles_user_id"),
    )
    op.create_index("ix_user_personalization_profiles_user_id", "user_personalization_profiles", ["user_id"], unique=False)
    op.create_index("ix_user_personalization_profiles_onboarding_state", "user_personalization_profiles", ["onboarding_state"], unique=False)


def downgrade():
    op.drop_index("ix_user_personalization_profiles_onboarding_state", table_name="user_personalization_profiles")
    op.drop_index("ix_user_personalization_profiles_user_id", table_name="user_personalization_profiles")
    op.drop_table("user_personalization_profiles")
