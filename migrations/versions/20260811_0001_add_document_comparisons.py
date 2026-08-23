"""add document comparison foundation

Revision ID: 20260811_0001
Revises: 20260810_0002
Create Date: 2026-08-11 00:56:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260811_0001"
down_revision = "20260810_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_comparisons",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "document_a_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "document_b_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "summary",
            sa.UnicodeText(),
            nullable=True,
        ),
        sa.Column(
            "findings_json",
            sa.UnicodeText(),
            nullable=True,
        ),
        sa.Column(
            "provider",
            sa.Unicode(length=30),
            nullable=False,
        ),
        sa.Column(
            "model",
            sa.Unicode(length=100),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Unicode(length=20),
            nullable=False,
        ),
        sa.Column(
            "source_fingerprint",
            sa.Unicode(length=64),
            nullable=True,
        ),
        sa.Column(
            "error_message",
            sa.UnicodeText(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),

        sa.CheckConstraint(
            "document_a_id <> document_b_id",
            name="ck_document_comparisons_distinct_documents",
        ),

        # One user -> comparisons cascade is safe.
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),

        # SQL Server rejects two cascading document paths into this table.
        # Keep A/B symmetric and let LifeOS explicitly clean comparison rows
        # before deleting a source document/project.
        sa.ForeignKeyConstraint(
            ["document_a_id"],
            ["documents.id"],
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["document_b_id"],
            ["documents.id"],
            ondelete="NO ACTION",
        ),

        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_document_comparisons_user_id"),
        "document_comparisons",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_document_comparisons_document_a_id"),
        "document_comparisons",
        ["document_a_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_document_comparisons_document_b_id"),
        "document_comparisons",
        ["document_b_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_document_comparisons_status"),
        "document_comparisons",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_document_comparisons_reuse",
        "document_comparisons",
        [
            "user_id",
            "document_a_id",
            "document_b_id",
            "status",
            "source_fingerprint",
        ],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_document_comparisons_reuse",
        table_name="document_comparisons",
    )

    op.drop_index(
        op.f("ix_document_comparisons_status"),
        table_name="document_comparisons",
    )

    op.drop_index(
        op.f("ix_document_comparisons_document_b_id"),
        table_name="document_comparisons",
    )

    op.drop_index(
        op.f("ix_document_comparisons_document_a_id"),
        table_name="document_comparisons",
    )

    op.drop_index(
        op.f("ix_document_comparisons_user_id"),
        table_name="document_comparisons",
    )

    op.drop_table(
        "document_comparisons"
    )
