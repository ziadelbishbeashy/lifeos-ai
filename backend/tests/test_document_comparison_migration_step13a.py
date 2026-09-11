"""Step 13A migration contract tests."""

from pathlib import Path


ROOT = Path(
    __file__
).resolve().parents[1]

MIGRATION = (
    ROOT
    / "migrations"
    / "versions"
    / "20260811_0001_add_document_comparisons.py"
)


def test_migration_follows_step12_head():
    text = MIGRATION.read_text(
        encoding="utf-8"
    )

    assert 'revision = "20260811_0001"' in text
    assert 'down_revision = "20260810_0002"' in text


def test_sql_server_document_foreign_keys_do_not_cascade():
    text = MIGRATION.read_text(
        encoding="utf-8"
    )

    # Both document FKs must be NO ACTION to avoid SQL Server error 1785.
    assert text.count('ondelete="NO ACTION"') == 2

    # User cleanup still cascades.
    assert text.count('ondelete="CASCADE"') == 1


def test_migration_has_distinct_document_constraint_and_reuse_index():
    text = MIGRATION.read_text(
        encoding="utf-8"
    )

    assert (
        "ck_document_comparisons_distinct_documents"
        in text
    )
    assert (
        "ix_document_comparisons_reuse"
        in text
    )
