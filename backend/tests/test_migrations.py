"""Database migration foundation tests."""

from pathlib import Path

from app import create_app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_migrate_extension_is_registered():
    app = create_app("testing")

    assert "migrate" in app.extensions


def test_baseline_revision_is_present():
    baseline = (
        PROJECT_ROOT
        / "migrations"
        / "versions"
        / "20260726_0001_existing_schema_baseline.py"
    )

    assert baseline.is_file()
    assert 'revision = "20260726_0001"' in baseline.read_text(encoding="utf-8")
