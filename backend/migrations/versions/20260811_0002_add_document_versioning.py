"""add document versioning

Revision ID: 20260811_0002
Revises: 20260811_0001
Create Date: 2026-08-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260811_0002"
down_revision = "20260811_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_version_families",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.Unicode(length=255),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_document_version_families_project_id"),
        "document_version_families",
        ["project_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_document_version_families_user_id"),
        "document_version_families",
        ["user_id"],
        unique=False,
    )

    op.add_column(
        "documents",
        sa.Column(
            "version_family_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "version_number",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "is_current_version",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "version_change_json",
            sa.UnicodeText(),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "superseded_at",
            sa.DateTime(),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_documents_version_family",
        "documents",
        "document_version_families",
        ["version_family_id"],
        ["id"],
        ondelete="NO ACTION",
    )

    op.create_index(
        op.f("ix_documents_version_family_id"),
        "documents",
        ["version_family_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_documents_is_current_version"),
        "documents",
        ["is_current_version"],
        unique=False,
    )

    op.create_index(
        "ix_documents_version_family_current",
        "documents",
        [
            "version_family_id",
            "is_current_version",
            "version_number",
        ],
        unique=False,
    )

def downgrade():
    op.drop_index(
        "ix_documents_version_family_current",
        table_name="documents",
    )

    op.drop_index(
        op.f("ix_documents_is_current_version"),
        table_name="documents",
    )

    op.drop_index(
        op.f("ix_documents_version_family_id"),
        table_name="documents",
    )

    op.drop_constraint(
        "fk_documents_version_family",
        "documents",
        type_="foreignkey",
    )

    op.drop_column(
        "documents",
        "superseded_at",
    )

    op.drop_column(
        "documents",
        "version_change_json",
    )

    op.drop_column(
        "documents",
        "is_current_version",
    )

    op.drop_column(
        "documents",
        "version_number",
    )

    op.drop_column(
        "documents",
        "version_family_id",
    )

    op.drop_index(
        op.f("ix_document_version_families_user_id"),
        table_name="document_version_families",
    )

    op.drop_index(
        op.f("ix_document_version_families_project_id"),
        table_name="document_version_families",
    )

    op.drop_table(
        "document_version_families"
    )
