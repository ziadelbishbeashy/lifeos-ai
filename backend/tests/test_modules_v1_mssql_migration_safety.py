from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_0003 = ROOT / "migrations" / "versions" / "20260828_0003_add_modules_v1_foundation.py"
MIGRATION_0004 = ROOT / "migrations" / "versions" / "20260828_0004_repair_document_owner_schema.py"


def test_modules_v1_0003_handles_mssql_alter_column_dependencies():
    source = MIGRATION_0003.read_text(encoding="utf-8")
    assert "_drop_column_dependencies_for_mssql" in source
    assert 'op.drop_index(idx["name"], table_name=table_name)' in source
    assert 'op.drop_constraint(fk["name"], table_name, type_="foreignkey")' in source
    assert "_restore_column_dependencies" in source
    assert '_alter_nullable(bind, "documents", "user_id", nullable=False)' in source
    assert '_alter_nullable(bind, "document_version_families", "project_id", nullable=True)' in source


def test_modules_v1_0003_reconciles_tables_precreated_by_create_all():
    source = MIGRATION_0003.read_text(encoding="utf-8")
    assert "_create_table_if_missing" in source
    for table in (
        "learning_modules",
        "lectures",
        "module_document_links",
        "module_note_links",
        "module_task_links",
        "module_collection_links",
        "module_questions",
    ):
        assert f'"{table}"' in source


def test_modules_v1_0004_repair_is_mssql_dependency_safe_too():
    source = MIGRATION_0004.read_text(encoding="utf-8")
    assert "_drop_mssql_column_dependencies" in source
    assert "_restore_mssql_column_dependencies" in source
    assert '_alter_integer_nullable(bind, "documents", "user_id", nullable=False)' in source
    assert '"document_version_families", "project_id", nullable=True' in source
