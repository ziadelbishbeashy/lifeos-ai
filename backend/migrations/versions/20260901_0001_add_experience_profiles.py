"""add adaptive user experience profiles

Revision ID: 20260901_0001
Revises: 20260831_0002
Create Date: 2026-09-01

Experience profiles personalize defaults and navigation without forking LifeOS
or duplicating domain data. Existing users intentionally remain unconfigured
until they choose an experience once during onboarding.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260901_0001"
down_revision = "20260831_0002"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _indexes(bind, table: str) -> set[str]:
    return {str(item.get("name")) for item in sa.inspect(bind).get_indexes(table) if item.get("name")}


def upgrade():
    bind = op.get_bind()
    if "user_experience_profiles" not in _tables(bind):
        op.create_table(
            "user_experience_profiles",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("primary_experience", sa.Unicode(length=40), nullable=True),
            sa.Column("enabled_experiences_json", sa.UnicodeText(), nullable=False, server_default="[]"),
            sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.ForeignKeyConstraint(
                ["user_id"], ["users.id"], ondelete="NO ACTION", name="fk_user_experience_profiles_user_id"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", name="uq_user_experience_profiles_user_id"),
        )

    existing = _indexes(bind, "user_experience_profiles")
    for name, columns in (
        ("ix_user_experience_profiles_primary_experience", ["primary_experience"]),
    ):
        if name not in existing:
            op.create_index(name, "user_experience_profiles", columns, unique=False)


def downgrade():
    bind = op.get_bind()
    if "user_experience_profiles" not in _tables(bind):
        return
    existing = _indexes(bind, "user_experience_profiles")
    for name in (
        "ix_user_experience_profiles_primary_experience",
    ):
        if name in existing:
            op.drop_index(name, table_name="user_experience_profiles")
    op.drop_table("user_experience_profiles")
