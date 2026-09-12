"""V-SPACE Authentication V1

Revision ID: 20260912_0003
Revises: 20260912_0002
"""
from alembic import op
import sqlalchemy as sa

revision = "20260912_0003"
down_revision = "20260912_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(), nullable=True))
    op.alter_column("users", "password_hash", existing_type=sa.Unicode(length=255), nullable=True)

    op.create_table(
        "user_auth_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.Unicode(length=32), nullable=False),
        sa.Column("provider_subject", sa.Unicode(length=255), nullable=False),
        sa.Column("provider_email", sa.Unicode(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_subject", name="uq_user_auth_identities_provider_subject"),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_auth_identities_user_provider"),
    )
    op.create_index("ix_user_auth_identities_user_id", "user_auth_identities", ["user_id"], unique=False)

    op.create_table(
        "user_auth_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.Unicode(length=32), nullable=False),
        sa.Column("token_hash", sa.Unicode(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_user_auth_tokens_token_hash"),
    )
    op.create_index("ix_user_auth_tokens_user_id", "user_auth_tokens", ["user_id"], unique=False)
    op.create_index("ix_user_auth_tokens_purpose", "user_auth_tokens", ["purpose"], unique=False)
    op.create_index("ix_user_auth_tokens_token_hash", "user_auth_tokens", ["token_hash"], unique=True)
    op.create_index("ix_user_auth_tokens_expires_at", "user_auth_tokens", ["expires_at"], unique=False)

    op.create_table(
        "user_auth_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.Unicode(length=64), nullable=False),
        sa.Column("auth_method", sa.Unicode(length=24), nullable=False, server_default="password"),
        sa.Column("remember", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("user_agent", sa.Unicode(length=320), nullable=True),
        sa.Column("ip_hash", sa.Unicode(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_user_auth_sessions_token_hash"),
    )
    op.create_index("ix_user_auth_sessions_user_id", "user_auth_sessions", ["user_id"], unique=False)
    op.create_index("ix_user_auth_sessions_token_hash", "user_auth_sessions", ["token_hash"], unique=True)
    op.create_index("ix_user_auth_sessions_expires_at", "user_auth_sessions", ["expires_at"], unique=False)
    op.create_index("ix_user_auth_sessions_revoked_at", "user_auth_sessions", ["revoked_at"], unique=False)

    op.create_table(
        "auth_rate_limit_buckets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bucket_key", sa.Unicode(length=96), nullable=False),
        sa.Column("window_started_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked_until", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bucket_key", name="uq_auth_rate_limit_buckets_bucket_key"),
    )
    op.create_index("ix_auth_rate_limit_buckets_bucket_key", "auth_rate_limit_buckets", ["bucket_key"], unique=True)
    op.create_index("ix_auth_rate_limit_buckets_blocked_until", "auth_rate_limit_buckets", ["blocked_until"], unique=False)


def downgrade():
    op.drop_index("ix_auth_rate_limit_buckets_blocked_until", table_name="auth_rate_limit_buckets")
    op.drop_index("ix_auth_rate_limit_buckets_bucket_key", table_name="auth_rate_limit_buckets")
    op.drop_table("auth_rate_limit_buckets")

    op.drop_index("ix_user_auth_sessions_revoked_at", table_name="user_auth_sessions")
    op.drop_index("ix_user_auth_sessions_expires_at", table_name="user_auth_sessions")
    op.drop_index("ix_user_auth_sessions_token_hash", table_name="user_auth_sessions")
    op.drop_index("ix_user_auth_sessions_user_id", table_name="user_auth_sessions")
    op.drop_table("user_auth_sessions")

    op.drop_index("ix_user_auth_tokens_expires_at", table_name="user_auth_tokens")
    op.drop_index("ix_user_auth_tokens_token_hash", table_name="user_auth_tokens")
    op.drop_index("ix_user_auth_tokens_purpose", table_name="user_auth_tokens")
    op.drop_index("ix_user_auth_tokens_user_id", table_name="user_auth_tokens")
    op.drop_table("user_auth_tokens")

    op.drop_index("ix_user_auth_identities_user_id", table_name="user_auth_identities")
    op.drop_table("user_auth_identities")

    op.alter_column("users", "password_hash", existing_type=sa.Unicode(length=255), nullable=False)
    op.drop_column("users", "email_verified_at")
