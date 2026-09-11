"""Add document chunks.

Revision ID: 2c300e7e2116
Revises: adafbc6a93cc
"""

from alembic import op
import sqlalchemy as sa


revision = "2c300e7e2116"
down_revision = "adafbc6a93cc"
branch_labels = None
depends_on = None


def upgrade():
    """Create only the document_chunks table."""

    connection = op.get_bind()
    inspector = sa.inspect(connection)

    existing_tables = set(
        inspector.get_table_names()
    )

    if "document_chunks" not in existing_tables:
        op.create_table(
            "document_chunks",

            sa.Column(
                "id",
                sa.Integer(),
                nullable=False,
            ),

            sa.Column(
                "document_id",
                sa.Integer(),
                nullable=False,
            ),

            sa.Column(
                "user_id",
                sa.Integer(),
                nullable=False,
            ),

            sa.Column(
                "chunk_index",
                sa.Integer(),
                nullable=False,
            ),

            sa.Column(
                "page_start",
                sa.Integer(),
                nullable=True,
            ),

            sa.Column(
                "page_end",
                sa.Integer(),
                nullable=True,
            ),

            sa.Column(
                "section_title",
                sa.Unicode(length=255),
                nullable=True,
            ),

            sa.Column(
                "text",
                sa.UnicodeText(),
                nullable=False,
            ),

            sa.Column(
                "character_count",
                sa.Integer(),
                nullable=False,
            ),

            sa.Column(
                "source_fingerprint",
                sa.Unicode(length=64),
                nullable=False,
            ),

            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
            ),

            sa.ForeignKeyConstraint(
                ["document_id"],
                ["documents.id"],
            ),

            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
            ),

            sa.PrimaryKeyConstraint(
                "id",
            ),

            sa.UniqueConstraint(
                "document_id",
                "chunk_index",
                name="uq_document_chunk_index",
            ),
        )

    # Refresh inspection after creating the table.
    inspector = sa.inspect(connection)

    existing_indexes = {
        index["name"]
        for index in inspector.get_indexes(
            "document_chunks"
        )
    }

    if (
        "ix_document_chunks_document_id"
        not in existing_indexes
    ):
        op.create_index(
            "ix_document_chunks_document_id",
            "document_chunks",
            ["document_id"],
            unique=False,
        )

    if (
        "ix_document_chunks_user_id"
        not in existing_indexes
    ):
        op.create_index(
            "ix_document_chunks_user_id",
            "document_chunks",
            ["user_id"],
            unique=False,
        )

    if (
        "ix_document_chunks_source_fingerprint"
        not in existing_indexes
    ):
        op.create_index(
            "ix_document_chunks_source_fingerprint",
            "document_chunks",
            ["source_fingerprint"],
            unique=False,
        )


def downgrade():
    """Remove only the document_chunks table."""

    connection = op.get_bind()
    inspector = sa.inspect(connection)

    existing_tables = set(
        inspector.get_table_names()
    )

    if "document_chunks" not in existing_tables:
        return

    existing_indexes = {
        index["name"]
        for index in inspector.get_indexes(
            "document_chunks"
        )
    }

    if (
        "ix_document_chunks_source_fingerprint"
        in existing_indexes
    ):
        op.drop_index(
            "ix_document_chunks_source_fingerprint",
            table_name="document_chunks",
        )

    if (
        "ix_document_chunks_user_id"
        in existing_indexes
    ):
        op.drop_index(
            "ix_document_chunks_user_id",
            table_name="document_chunks",
        )

    if (
        "ix_document_chunks_document_id"
        in existing_indexes
    ):
        op.drop_index(
            "ix_document_chunks_document_id",
            table_name="document_chunks",
        )

    op.drop_table(
        "document_chunks"
    )