"""Foundation V2 architecture contract tests."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_foundation_v2_package_exists():
    assert (ROOT / "lifeos" / "application.py").exists()
    assert (ROOT / "lifeos" / "api" / "v1" / "routes.py").exists()
    assert (ROOT / "lifeos" / "domains" / "documents").is_dir()


def test_legacy_entrypoint_is_only_a_compatibility_layer():
    text = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "from lifeos.application import create_app" in text


def test_postgres_driver_is_primary_requirement():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "psycopg[binary]" in requirements
    assert "pyodbc" not in requirements


def test_sql_server_driver_is_isolated_to_legacy_requirements():
    requirements = (
        ROOT / "requirements-legacy-sqlserver.txt"
    ).read_text(encoding="utf-8")
    assert "pyodbc" in requirements
