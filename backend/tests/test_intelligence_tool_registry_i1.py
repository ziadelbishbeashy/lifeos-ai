from __future__ import annotations

import pytest

from services.intelligence_tool_registry_service import (
    IntelligenceToolInputError,
    IntelligenceToolNotFoundError,
    IntelligenceToolPermissionError,
    IntelligenceToolRegistry,
    IntelligenceToolSpec,
    build_default_intelligence_tool_registry,
)


def test_default_intelligence_registry_is_read_only_and_explicit():
    registry = build_default_intelligence_tool_registry()
    contracts = registry.list_contracts()

    assert [item["name"] for item in contracts] == [
        "project.get_documents",
        "project.get_recent_notes",
        "project.get_summary",
        "project.get_tasks",
    ]
    assert all(item["risk"] == "read_only" for item in contracts)
    assert all(item["mutates_state"] is False for item in contracts)


def test_registry_fails_closed_for_unknown_tool():
    registry = IntelligenceToolRegistry()
    with pytest.raises(IntelligenceToolNotFoundError):
        registry.execute("database.query", owner_id=1, arguments={})


def test_registry_rejects_duplicate_tool_names():
    registry = IntelligenceToolRegistry()
    spec = IntelligenceToolSpec(
        name="safe.read",
        description="read",
        risk="read_only",
        scope="test",
        input_fields=(),
        handler=lambda **kwargs: {"ok": True},
    )
    registry.register(spec)
    with pytest.raises(IntelligenceToolInputError, match="already registered"):
        registry.register(spec)


def test_registry_requires_explicit_boundary_for_mutating_tool():
    registry = IntelligenceToolRegistry()
    registry.register(
        IntelligenceToolSpec(
            name="unsafe.write",
            description="write",
            risk="write",
            scope="test",
            input_fields=(),
            handler=lambda **kwargs: {"changed": True},
        )
    )

    with pytest.raises(IntelligenceToolPermissionError, match="explicit action boundary"):
        registry.execute("unsafe.write", owner_id=1, arguments={})
