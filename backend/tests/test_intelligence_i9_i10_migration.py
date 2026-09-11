from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "versions" / "20260829_0001_add_intelligence_actions_activity.py"


def test_i9_i10_migration_extends_current_head_with_new_tables_only():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260829_0001"' in source
    assert 'down_revision = "20260828_0004"' in source
    assert '"lifeos_action_proposals"' in source
    assert '"lifeos_activity_events"' in source
    assert "op.alter_column" not in source
    assert "ALTER TABLE" not in source


def test_i9_i10_history_project_ids_do_not_block_project_deletion():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "fk_lifeos_action_proposals_project_id" not in source
    assert "fk_lifeos_activity_events_project_id" not in source
