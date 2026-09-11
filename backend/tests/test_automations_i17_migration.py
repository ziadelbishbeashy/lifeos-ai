from pathlib import Path


def test_i17_preparation_migration_extends_i16_head_with_automation_tables():
    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "20260830_0001_prepare_lifeos_automations.py"
    text = path.read_text(encoding="utf-8")
    assert 'revision = "20260830_0001"' in text
    assert 'down_revision = "20260829_0004"' in text
    assert '"lifeos_automations"' in text
    assert '"lifeos_automation_runs"' in text
    assert '"enabled"' in text
    assert '"dry_run"' in text
