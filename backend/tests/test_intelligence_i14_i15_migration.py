from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "versions" / "20260829_0003_add_event_engine_proactive_notifications.py"


def test_i14_i15_migration_extends_i13_head_with_new_tables_only():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260829_0003"' in source
    assert 'down_revision = "20260829_0002"' in source
    assert '"lifeos_intelligence_events"' in source
    assert '"lifeos_proactive_notifications"' in source
    assert "op.alter_column" not in source
    assert "ALTER TABLE" not in source


def test_i14_events_keep_polymorphic_project_and_resource_ids_non_blocking():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "fk_lifeos_intelligence_events_project_id" not in source
    assert "fk_lifeos_intelligence_events_object_id" not in source
