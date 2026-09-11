"""repair direct document ownership schema after Modules V1 rollout

Revision ID: 20260828_0004
Revises: 20260828_0003
Create Date: 2026-08-28

This migration remains as a repair layer for databases that may already be
stamped at 20260828_0003 while still lacking part of the intended Modules V1
schema. Revision 0003 is also dependency-safe for fresh upgrades from 0002;
0004 protects already-drifted installations.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260828_0004"
down_revision = "20260828_0003"
branch_labels = None
depends_on = None


def _column(inspector, table_name: str, column_name: str):
    for column in inspector.get_columns(table_name):
        if column.get("name") == column_name:
            return column
    return None


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def _has_document_user_fk(inspector) -> bool:
    for foreign_key in inspector.get_foreign_keys("documents"):
        constrained = foreign_key.get("constrained_columns") or []
        referred_table = foreign_key.get("referred_table")
        referred = foreign_key.get("referred_columns") or []
        if constrained == ["user_id"] and referred_table == "users" and referred == ["id"]:
            return True
    return False


def _drop_mssql_column_dependencies(bind, table_name: str, column_name: str):
    if bind.dialect.name != "mssql":
        return [], []

    inspector = sa.inspect(bind)
    indexes = []
    for index in inspector.get_indexes(table_name):
        if column_name in (index.get("column_names") or []):
            name = index.get("name")
            if name:
                indexes.append({
                    "name": name,
                    "columns": list(index.get("column_names") or []),
                    "unique": bool(index.get("unique", False)),
                })

    foreign_keys = []
    for fk in inspector.get_foreign_keys(table_name):
        if (fk.get("constrained_columns") or []) == [column_name] and fk.get("name"):
            foreign_keys.append({
                "name": fk["name"],
                "referred_table": fk.get("referred_table"),
                "constrained_columns": list(fk.get("constrained_columns") or []),
                "referred_columns": list(fk.get("referred_columns") or []),
                "ondelete": (fk.get("options") or {}).get("ondelete"),
            })

    for fk in foreign_keys:
        op.drop_constraint(fk["name"], table_name, type_="foreignkey")
    for index in indexes:
        op.drop_index(index["name"], table_name=table_name)

    return indexes, foreign_keys


def _restore_mssql_column_dependencies(table_name: str, indexes, foreign_keys) -> None:
    for fk in foreign_keys:
        op.create_foreign_key(
            fk["name"],
            table_name,
            fk["referred_table"],
            fk["constrained_columns"],
            fk["referred_columns"],
            ondelete=fk.get("ondelete"),
        )
    for index in indexes:
        op.create_index(
            index["name"],
            table_name,
            index["columns"],
            unique=index.get("unique", False),
        )


def _alter_integer_nullable(bind, table_name: str, column_name: str, *, nullable: bool) -> None:
    indexes, foreign_keys = _drop_mssql_column_dependencies(
        bind, table_name, column_name
    )
    try:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table(table_name) as batch_op:
                batch_op.alter_column(
                    column_name,
                    existing_type=sa.Integer(),
                    nullable=nullable,
                )
        else:
            op.alter_column(
                table_name,
                column_name,
                existing_type=sa.Integer(),
                nullable=nullable,
            )
    finally:
        if bind.dialect.name == "mssql":
            _restore_mssql_column_dependencies(table_name, indexes, foreign_keys)


def _alter_documents_user_not_null(bind) -> None:
    _alter_integer_nullable(bind, "documents", "user_id", nullable=False)


def _alter_version_family_project_nullable(bind) -> None:
    _alter_integer_nullable(
        bind, "document_version_families", "project_id", nullable=True
    )


def _create_document_user_fk(bind) -> None:
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("documents") as batch_op:
            batch_op.create_foreign_key(
                "fk_documents_user_id_users",
                "users",
                ["user_id"],
                ["id"],
                ondelete="NO ACTION",
            )
    else:
        op.create_foreign_key(
            "fk_documents_user_id_users",
            "documents",
            "users",
            ["user_id"],
            ["id"],
            ondelete="NO ACTION",
        )


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "documents" not in inspector.get_table_names():
        raise RuntimeError("Cannot repair Modules V1 ownership: documents table is missing.")

    # 1) Restore the direct ownership column if a database was already stamped
    # at 0003 without receiving the matching schema change.
    user_column = _column(inspector, "documents", "user_id")
    if user_column is None:
        op.add_column("documents", sa.Column("user_id", sa.Integer(), nullable=True))

    # 2) Backfill every historical project/version document from authoritative
    # ownership that already existed before Modules V1.
    project_column = _column(sa.inspect(bind), "documents", "project_id")
    if project_column is not None:
        op.execute(
            sa.text(
                """
                UPDATE documents
                SET user_id = (
                    SELECT projects.user_id
                    FROM projects
                    WHERE projects.id = documents.project_id
                )
                WHERE user_id IS NULL
                  AND project_id IS NOT NULL
                """
            )
        )

    inspector = sa.inspect(bind)
    family_column = _column(inspector, "documents", "version_family_id")
    family_tables = inspector.get_table_names()
    if family_column is not None and "document_version_families" in family_tables:
        op.execute(
            sa.text(
                """
                UPDATE documents
                SET user_id = (
                    SELECT document_version_families.user_id
                    FROM document_version_families
                    WHERE document_version_families.id = documents.version_family_id
                )
                WHERE user_id IS NULL
                  AND version_family_id IS NOT NULL
                """
            )
        )

    # Do not invent ownership for genuinely orphaned historical rows.
    remaining = bind.execute(sa.text("SELECT COUNT(*) FROM documents WHERE user_id IS NULL")).scalar_one()
    if remaining:
        raise RuntimeError(
            "Cannot finish Modules V1 ownership repair: "
            f"{remaining} document row(s) have no project/version owner to backfill. "
            "Assign those rows to their real user before rerunning the migration."
        )

    # 3) Match the intended production invariant from 0003.
    inspector = sa.inspect(bind)
    user_column = _column(inspector, "documents", "user_id")
    if user_column is not None and user_column.get("nullable", True):
        _alter_documents_user_not_null(bind)

    inspector = sa.inspect(bind)
    expected_index_name = "ix_documents_user_id"
    if not _has_index(inspector, "documents", expected_index_name):
        op.create_index(expected_index_name, "documents", ["user_id"], unique=False)

    inspector = sa.inspect(bind)
    if not _has_document_user_fk(inspector):
        _create_document_user_fk(bind)

    # 4) Module/general documents are allowed to have a version family without
    # a Project. Repair this part of the 0003 contract too if the DB drifted.
    inspector = sa.inspect(bind)
    if "document_version_families" in inspector.get_table_names():
        project_family_column = _column(inspector, "document_version_families", "project_id")
        if project_family_column is not None and not project_family_column.get("nullable", True):
            _alter_version_family_project_nullable(bind)


def downgrade():
    # This is a schema-reconciliation revision. Reversing it would recreate the
    # broken state, so downgrade intentionally preserves the repaired schema.
    pass
