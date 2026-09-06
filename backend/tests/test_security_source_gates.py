"""Static security gates for backend/API architecture invariants.

These tests are intentionally narrow. They do not replace a penetration test;
they prevent a few high-impact regressions that are easy to introduce during
feature work.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re


BACKEND_DIR = Path(__file__).resolve().parents[1]
API_DIR = BACKEND_DIR / "lifeos" / "api" / "v1"

_PUBLIC_API_ROUTES = {
    ("routes.py", "get", "/health"),
    ("routes.py", "get", "/meta"),
    ("routes.py", "get", "/csrf"),
    ("routes.py", "get", "/session"),
    ("routes.py", "post", "/auth/login"),
    ("routes.py", "post", "/auth/register"),
    ("experience.py", "get", "/options"),
}
_HTTP_METHOD_DECORATORS = {"get", "post", "put", "patch", "delete"}


def _route_decorator(decorator: ast.expr):
    if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
        return None
    method = decorator.func.attr.casefold()
    if method not in _HTTP_METHOD_DECORATORS or not decorator.args:
        return None
    first = decorator.args[0]
    if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
        return None
    return method, first.value


def _has_api_auth_required(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == "api_auth_required":
            return True
    return False


def test_every_private_v1_api_route_requires_authentication():
    """Prevent both accidental writes *and reads* from becoming public.

    The allowlist is deliberately explicit so adding a new public endpoint is a
    reviewed security decision rather than an accidental missing decorator.
    """

    failures: list[str] = []
    for path in sorted(API_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            routes = [item for decorator in node.decorator_list if (item := _route_decorator(decorator))]
            for method, route in routes:
                if (path.name, method, route) in _PUBLIC_API_ROUTES:
                    continue
                if not _has_api_auth_required(node):
                    failures.append(f"{path.name}:{node.lineno} {method.upper()} {route}")

    assert not failures, "Private API routes missing @api_auth_required: " + ", ".join(failures)


def test_runtime_code_does_not_execute_fstring_sql():
    """Block the most obvious SQL-injection regression pattern.

    SQLAlchemy ORM/filter expressions remain allowed. Migrations are excluded
    because they contain reviewed schema DDL and are not request-time user input.
    """

    unsafe = re.compile(
        r"(?:session|connection|cursor|conn)\.execute\s*\(\s*f[\"']|"
        r"\btext\s*\(\s*f[\"']",
        re.MULTILINE,
    )
    failures: list[str] = []
    roots = [BACKEND_DIR / "services", BACKEND_DIR / "routes", BACKEND_DIR / "lifeos"]
    for root in roots:
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if unsafe.search(source):
                failures.append(str(path.relative_to(BACKEND_DIR)))

    assert not failures, "Potential f-string SQL execution found: " + ", ".join(failures)


def test_ai_reasoning_layers_have_no_direct_database_write_access():
    files = [
        BACKEND_DIR / "services" / "intelligence_reasoning_service.py",
        BACKEND_DIR / "services" / "agent_reasoning_service.py",
    ]
    failures: list[str] = []
    for path in files:
        source = path.read_text(encoding="utf-8")
        if "from database import" in source or "db.session" in source:
            failures.append(path.name)

    assert not failures, "Reasoning layers must remain DB-write-free: " + ", ".join(failures)
