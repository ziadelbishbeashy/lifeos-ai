from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "versions" / "20260828_0004_repair_document_owner_schema.py"


def test_modules_v1_schema_repair_revision_chain():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260828_0004"' in source
    assert 'down_revision = "20260828_0003"' in source


def test_modules_v1_schema_repair_restores_document_user_id_without_guessing_owner():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'op.add_column("documents", sa.Column("user_id", sa.Integer(), nullable=True))' in source
    assert "projects.user_id" in source
    assert "document_version_families.user_id" in source
    assert "SELECT COUNT(*) FROM documents WHERE user_id IS NULL" in source
    assert "Cannot finish Modules V1 ownership repair" in source


def test_modules_v1_schema_repair_restores_constraint_and_index():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "ix_documents_user_id" in source
    assert "fk_documents_user_id_users" in source
    assert '"users"' in source
    assert '["user_id"]' in source


def test_modules_v1_schema_repair_keeps_module_version_families_project_optional():
    source = MIGRATION.read_text(encoding="utf-8")
    assert '"document_version_families"' in source
    assert '"project_id"' in source
    assert "nullable=True" in source
