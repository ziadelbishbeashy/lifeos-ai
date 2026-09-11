"""add modules v1 foundation and direct document ownership

Revision ID: 20260828_0003
Revises: 20260828_0002
Create Date: 2026-08-28

This revision is intentionally defensive on SQL Server. Local development may
have run ``db.create_all()`` before Alembic, which can create the new Module
tables without altering existing tables such as ``documents``. The migration
therefore reconciles the expected schema instead of assuming every object is
absent.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260828_0003"
down_revision = "20260828_0002"
branch_labels = None
depends_on = None


def _column(inspector, table_name: str, column_name: str):
    for column in inspector.get_columns(table_name):
        if column.get("name") == column_name:
            return column
    return None


def _index(inspector, table_name: str, index_name: str):
    for index in inspector.get_indexes(table_name):
        if index.get("name") == index_name:
            return index
    return None


def _fk_for_column(inspector, table_name: str, column_name: str):
    matches = []
    for fk in inspector.get_foreign_keys(table_name):
        if (fk.get("constrained_columns") or []) == [column_name]:
            matches.append(fk)
    return matches


def _drop_column_dependencies_for_mssql(bind, table_name: str, column_name: str):
    """Temporarily remove single-column indexes/FKs that block ALTER COLUMN."""
    if bind.dialect.name != "mssql":
        return [], []

    inspector = sa.inspect(bind)
    indexes = []
    for idx in inspector.get_indexes(table_name):
        if column_name in (idx.get("column_names") or []):
            name = idx.get("name")
            if name:
                indexes.append({
                    "name": name,
                    "columns": list(idx.get("column_names") or []),
                    "unique": bool(idx.get("unique", False)),
                })

    foreign_keys = []
    for fk in _fk_for_column(inspector, table_name, column_name):
        name = fk.get("name")
        if name:
            foreign_keys.append({
                "name": name,
                "referred_table": fk.get("referred_table"),
                "constrained_columns": list(fk.get("constrained_columns") or []),
                "referred_columns": list(fk.get("referred_columns") or []),
                "ondelete": (fk.get("options") or {}).get("ondelete"),
            })

    for fk in foreign_keys:
        op.drop_constraint(fk["name"], table_name, type_="foreignkey")
    for idx in indexes:
        op.drop_index(idx["name"], table_name=table_name)

    return indexes, foreign_keys


def _restore_column_dependencies(table_name: str, indexes, foreign_keys):
    for fk in foreign_keys:
        op.create_foreign_key(
            fk["name"],
            table_name,
            fk["referred_table"],
            fk["constrained_columns"],
            fk["referred_columns"],
            ondelete=fk.get("ondelete"),
        )
    for idx in indexes:
        op.create_index(
            idx["name"],
            table_name,
            idx["columns"],
            unique=idx.get("unique", False),
        )


def _alter_nullable(bind, table_name: str, column_name: str, nullable: bool):
    indexes, foreign_keys = _drop_column_dependencies_for_mssql(
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
            _restore_column_dependencies(table_name, indexes, foreign_keys)


def _ensure_index(bind, table_name: str, index_name: str, columns):
    inspector = sa.inspect(bind)
    if _index(inspector, table_name, index_name) is None:
        op.create_index(index_name, table_name, columns, unique=False)


def _ensure_document_user_fk(bind):
    inspector = sa.inspect(bind)
    for fk in inspector.get_foreign_keys("documents"):
        if (fk.get("constrained_columns") or []) == ["user_id"]:
            if fk.get("referred_table") == "users" and (fk.get("referred_columns") or []) == ["id"]:
                return
    op.create_foreign_key(
        "fk_documents_user_id_users",
        "documents",
        "users",
        ["user_id"],
        ["id"],
        ondelete="NO ACTION",
    )


def _create_table_if_missing(bind, table_name: str, *columns_and_constraints):
    if table_name in sa.inspect(bind).get_table_names():
        return False
    op.create_table(table_name, *columns_and_constraints)
    return True


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Documents were historically owned indirectly through Project. Modules are
    # a separate workspace type, so ownership must live on the shared Document
    # itself. Existing rows are backfilled before the column becomes required.
    if _column(inspector, "documents", "user_id") is None:
        op.add_column("documents", sa.Column("user_id", sa.Integer(), nullable=True))

    op.execute(
        """
        UPDATE d
        SET d.user_id = p.user_id
        FROM documents AS d
        INNER JOIN projects AS p ON p.id = d.project_id
        WHERE d.user_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE d
        SET d.user_id = f.user_id
        FROM documents AS d
        INNER JOIN document_version_families AS f ON f.id = d.version_family_id
        WHERE d.user_id IS NULL
        """
    )

    remaining = bind.execute(
        sa.text("SELECT COUNT(*) FROM documents WHERE user_id IS NULL")
    ).scalar_one()
    if remaining:
        raise RuntimeError(
            "Cannot enable direct document ownership: "
            f"{remaining} document row(s) have no project/version owner to backfill."
        )

    inspector = sa.inspect(bind)
    user_column = _column(inspector, "documents", "user_id")
    if user_column is not None and user_column.get("nullable", True):
        # SQL Server does not allow ALTER COLUMN while ix_documents_user_id (or
        # an FK/index created by db.create_all) depends on the column. Temporarily
        # remove those dependencies, alter, then restore them.
        _alter_nullable(bind, "documents", "user_id", nullable=False)

    _ensure_index(bind, "documents", "ix_documents_user_id", ["user_id"])
    _ensure_document_user_fk(bind)

    # Version families can now belong to a user-owned Module/general document,
    # so a Project association is no longer mandatory. SQL Server can also
    # block this ALTER when the existing project_id index/FK is present, so the
    # same dependency-safe helper is used.
    inspector = sa.inspect(bind)
    family_project = _column(inspector, "document_version_families", "project_id")
    if family_project is not None and not family_project.get("nullable", True):
        _alter_nullable(bind, "document_version_families", "project_id", nullable=True)

    created = _create_table_if_missing(
        bind,
        "learning_modules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Unicode(length=150), nullable=False),
        sa.Column("description", sa.UnicodeText(), nullable=True),
        sa.Column("subject", sa.Unicode(length=150), nullable=True),
        sa.Column("status", sa.Unicode(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="NO ACTION"),
        sa.PrimaryKeyConstraint("id"),
    )
    if created:
        op.create_index(op.f("ix_learning_modules_user_id"), "learning_modules", ["user_id"], unique=False)
        op.create_index(op.f("ix_learning_modules_status"), "learning_modules", ["status"], unique=False)

    created = _create_table_if_missing(
        bind,
        "lectures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Unicode(length=180), nullable=False),
        sa.Column("lecture_number", sa.Integer(), nullable=True),
        sa.Column("lecture_date", sa.Date(), nullable=True),
        sa.Column("status", sa.Unicode(length=32), nullable=False),
        sa.Column("topics", sa.UnicodeText(), nullable=True),
        sa.Column("summary", sa.UnicodeText(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["module_id"], ["learning_modules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("module_id", "lecture_number", name="uq_module_lecture_number"),
    )
    if created:
        op.create_index(op.f("ix_lectures_module_id"), "lectures", ["module_id"], unique=False)
        op.create_index(op.f("ix_lectures_status"), "lectures", ["status"], unique=False)

    created = _create_table_if_missing(
        bind,
        "module_document_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("lecture_id", sa.Integer(), nullable=True),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["module_id"], ["learning_modules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lecture_id"], ["lectures.id"], ondelete="NO ACTION"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("module_id", "document_id", name="uq_module_document_link"),
    )
    if created:
        op.create_index(op.f("ix_module_document_links_module_id"), "module_document_links", ["module_id"], unique=False)
        op.create_index(op.f("ix_module_document_links_document_id"), "module_document_links", ["document_id"], unique=False)
        op.create_index(op.f("ix_module_document_links_lecture_id"), "module_document_links", ["lecture_id"], unique=False)

    created = _create_table_if_missing(
        bind,
        "module_note_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("note_id", sa.Integer(), nullable=False),
        sa.Column("lecture_id", sa.Integer(), nullable=True),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["module_id"], ["learning_modules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lecture_id"], ["lectures.id"], ondelete="NO ACTION"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("module_id", "note_id", name="uq_module_note_link"),
    )
    if created:
        op.create_index(op.f("ix_module_note_links_module_id"), "module_note_links", ["module_id"], unique=False)
        op.create_index(op.f("ix_module_note_links_note_id"), "module_note_links", ["note_id"], unique=False)
        op.create_index(op.f("ix_module_note_links_lecture_id"), "module_note_links", ["lecture_id"], unique=False)

    created = _create_table_if_missing(
        bind,
        "module_task_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("lecture_id", sa.Integer(), nullable=True),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["module_id"], ["learning_modules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lecture_id"], ["lectures.id"], ondelete="NO ACTION"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("module_id", "task_id", name="uq_module_task_link"),
    )
    if created:
        op.create_index(op.f("ix_module_task_links_module_id"), "module_task_links", ["module_id"], unique=False)
        op.create_index(op.f("ix_module_task_links_task_id"), "module_task_links", ["task_id"], unique=False)
        op.create_index(op.f("ix_module_task_links_lecture_id"), "module_task_links", ["lecture_id"], unique=False)

    created = _create_table_if_missing(
        bind,
        "module_collection_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["module_id"], ["learning_modules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["collection_id"], ["document_collections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("module_id", "collection_id", name="uq_module_collection_link"),
    )
    if created:
        op.create_index(op.f("ix_module_collection_links_module_id"), "module_collection_links", ["module_id"], unique=False)
        op.create_index(op.f("ix_module_collection_links_collection_id"), "module_collection_links", ["collection_id"], unique=False)

    created = _create_table_if_missing(
        bind,
        "module_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("lecture_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["module_id"], ["learning_modules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lecture_id"], ["lectures.id"], ondelete="NO ACTION"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="NO ACTION"),
        sa.PrimaryKeyConstraint("id"),
    )
    if created:
        op.create_index(op.f("ix_module_questions_module_id"), "module_questions", ["module_id"], unique=False)
        op.create_index(op.f("ix_module_questions_lecture_id"), "module_questions", ["lecture_id"], unique=False)
        op.create_index(op.f("ix_module_questions_user_id"), "module_questions", ["user_id"], unique=False)
        op.create_index(op.f("ix_module_questions_status"), "module_questions", ["status"], unique=False)


def downgrade():
    # Downgrade remains intended for a migration-managed schema. It is not used
    # as a cleanup mechanism for tables that may have pre-existed via create_all.
    op.drop_index(op.f("ix_module_questions_status"), table_name="module_questions")
    op.drop_index(op.f("ix_module_questions_user_id"), table_name="module_questions")
    op.drop_index(op.f("ix_module_questions_lecture_id"), table_name="module_questions")
    op.drop_index(op.f("ix_module_questions_module_id"), table_name="module_questions")
    op.drop_table("module_questions")

    op.drop_index(op.f("ix_module_collection_links_collection_id"), table_name="module_collection_links")
    op.drop_index(op.f("ix_module_collection_links_module_id"), table_name="module_collection_links")
    op.drop_table("module_collection_links")

    op.drop_index(op.f("ix_module_task_links_lecture_id"), table_name="module_task_links")
    op.drop_index(op.f("ix_module_task_links_task_id"), table_name="module_task_links")
    op.drop_index(op.f("ix_module_task_links_module_id"), table_name="module_task_links")
    op.drop_table("module_task_links")

    op.drop_index(op.f("ix_module_note_links_lecture_id"), table_name="module_note_links")
    op.drop_index(op.f("ix_module_note_links_note_id"), table_name="module_note_links")
    op.drop_index(op.f("ix_module_note_links_module_id"), table_name="module_note_links")
    op.drop_table("module_note_links")

    op.drop_index(op.f("ix_module_document_links_lecture_id"), table_name="module_document_links")
    op.drop_index(op.f("ix_module_document_links_document_id"), table_name="module_document_links")
    op.drop_index(op.f("ix_module_document_links_module_id"), table_name="module_document_links")
    op.drop_table("module_document_links")

    op.drop_index(op.f("ix_lectures_status"), table_name="lectures")
    op.drop_index(op.f("ix_lectures_module_id"), table_name="lectures")
    op.drop_table("lectures")

    op.drop_index(op.f("ix_learning_modules_status"), table_name="learning_modules")
    op.drop_index(op.f("ix_learning_modules_user_id"), table_name="learning_modules")
    op.drop_table("learning_modules")

    bind = op.get_bind()
    _alter_nullable(bind, "document_version_families", "project_id", nullable=False)

    inspector = sa.inspect(bind)
    for fk in _fk_for_column(inspector, "documents", "user_id"):
        if fk.get("name"):
            op.drop_constraint(fk["name"], "documents", type_="foreignkey")
    if _index(sa.inspect(bind), "documents", "ix_documents_user_id") is not None:
        op.drop_index("ix_documents_user_id", table_name="documents")
    if _column(sa.inspect(bind), "documents", "user_id") is not None:
        op.drop_column("documents", "user_id")
