"""Regression checks for standalone Alembic bootstrap."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_database_compatibility_module_imports_without_booting_flask_app():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from database import db, normalize_database_uri; "
                "assert db is not None; "
                "assert normalize_database_uri('postgres://a') == "
                "'postgresql+psycopg://a'"
            ),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_standalone_alembic_environment_boots_without_flask_context():
    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite:///:memory:"
    env["DATABASE_DIRECT_URL"] = "sqlite:///:memory:"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "migrations/alembic.ini",
            "current",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
