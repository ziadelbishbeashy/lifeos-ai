"""SQL Server regression guards for Boolean/BIT predicates."""

from __future__ import annotations

import ast
from pathlib import Path

from sqlalchemy.dialects import mssql

from services.document_version_service import current_document_filter


def test_current_document_filter_compiles_to_mssql_bit_equality():
    sql = str(
        current_document_filter().compile(
            dialect=mssql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).upper()

    assert "IS_CURRENT_VERSION = 1" in sql
    assert "IS_CURRENT_VERSION IS 1" not in sql
    assert "IS_CURRENT_VERSION IS 0" not in sql


def test_services_do_not_use_is_with_python_boolean_literals():
    """Keep .is_(None) valid while rejecting .is_(True/False) on BIT fields."""

    services_dir = Path(__file__).resolve().parents[1] / "services"
    violations: list[str] = []

    for path in services_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"is_", "isnot", "is_not"} or not node.args:
                continue
            argument = node.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, bool):
                violations.append(f"{path.name}:{node.lineno}")

    assert violations == []
