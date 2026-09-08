from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import Boolean, Column, ForeignKey, Integer, MetaData, String, Table


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "migrate_mssql_to_postgres.py"
SPEC = importlib.util.spec_from_file_location("lifeos_mssql_to_postgres_migration", SCRIPT_PATH)
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


def test_migration_skips_only_nonpersistent_control_tables():
    assert module.SKIP_TABLES == {"alembic_version", "ai_operation_locks"}


def test_fk_order_places_parent_before_child_and_ignores_self_fk():
    metadata = MetaData()
    users = Table("users", metadata, Column("id", Integer, primary_key=True))
    projects = Table(
        "projects",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("user_id", Integer, ForeignKey("users.id")),
    )
    tasks = Table(
        "tasks",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("project_id", Integer, ForeignKey("projects.id")),
        Column("parent_task_id", Integer, ForeignKey("tasks.id"), nullable=True),
    )

    ordered = module._topological_order(
        {"users": users, "projects": projects, "tasks": tasks},
        ["tasks", "users", "projects"],
    )
    assert ordered.index("users") < ordered.index("projects") < ordered.index("tasks")


def test_fk_order_fails_closed_on_cross_table_cycle():
    # Construct a tiny fake graph via simple table-like objects because SQLAlchemy
    # itself rejects unresolved cyclic declaration details at construction time.
    class Referred:
        def __init__(self, name):
            self.name = name

    class FK:
        def __init__(self, parent):
            self.referred_table = Referred(parent)

    class FakeTable:
        def __init__(self, *parents):
            self.foreign_key_constraints = [FK(parent) for parent in parents]

    with pytest.raises(module.MigrationError, match="cycle"):
        module._topological_order({"a": FakeTable("b"), "b": FakeTable("a")}, ["a", "b"])


def test_boolean_values_are_normalized_for_postgres():
    metadata = MetaData()
    table = Table("flags", metadata, Column("enabled", Boolean))
    assert module._normalize_value(1, table.c.enabled) is True
    assert module._normalize_value(0, table.c.enabled) is False
    assert module._normalize_value(None, table.c.enabled) is None


def test_target_url_rejects_neon_pooler():
    source = "mssql+pyodbc:///?odbc_connect=x"
    target = "postgresql+psycopg://u:p@ep-example-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require"
    with pytest.raises(module.MigrationError, match="direct connection"):
        module._validate_engine_urls(source, target)


def test_target_url_requires_tls():
    source = "mssql+pyodbc:///?odbc_connect=x"
    target = "postgresql+psycopg://u:p@ep-example.eu-central-1.aws.neon.tech/neondb"
    with pytest.raises(module.MigrationError, match="TLS"):
        module._validate_engine_urls(source, target)
