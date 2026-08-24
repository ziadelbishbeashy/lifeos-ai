"""Step 14 SQL Server migration contract tests."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "migrations"
    / "versions"
    / "20260811_0002_add_document_versioning.py"
)


def test_step14_migration_follows_step13():
    text = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260811_0002"' in text
    assert 'down_revision = "20260811_0001"' in text


def test_versioning_migration_is_sql_server_no_action_safe():
    text = MIGRATION.read_text(encoding="utf-8")
    assert text.count('ondelete="NO ACTION"') == 3
    assert "document_version_families" in text
    assert "version_family_id" in text
    assert "is_current_version" in text
    assert "version_change_json" in text
