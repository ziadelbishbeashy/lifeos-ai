"""Step 12 migration contract test."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_step12_project_questions_migration_is_chained_after_step9():
    migration = (
        ROOT / "migrations" / "versions" / "20260810_0002_add_project_questions.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260810_0002"' in migration
    assert 'down_revision = "20260810_0001"' in migration
    assert '"project_questions"' in migration
