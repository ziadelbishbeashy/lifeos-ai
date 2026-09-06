from __future__ import annotations

import pytest

from database import db
from models import LifeOSActionProposal, LifeOSAgentRun, Project, Task
from services.agent_reasoning_service import AgentReasoningItem, AgentReasoningResult


def _project(owner_id: int, title: str = "LangGraph I19") -> Project:
    row = Project(
        user_id=owner_id,
        title=title,
        status="In Progress",
        priority="High",
        progress=40,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _fake_reasoning(**kwargs):
    evidence = kwargs["evidence_catalog"]
    evidence_id = evidence[0]["id"]
    return AgentReasoningResult(
        answer="The project has a verified priority that should be addressed next.",
        claims=(AgentReasoningItem("A verified priority exists.", (evidence_id,)),),
        recommendations=(AgentReasoningItem("Handle the highest-ranked priority first.", (evidence_id,)),),
        provider="test",
        model="test-model",
    )


def test_langgraph_is_opt_in_and_legacy_remains_default(monkeypatch):
    monkeypatch.delenv("AI_LANGGRAPH_I19_ENABLED", raising=False)
    monkeypatch.setattr(
        "services.agent_execution_service.run_owned_agent_goal_legacy",
        lambda **kwargs: {"runtime": "legacy", "owner_id": kwargs["owner_id"]},
    )
    from services.agent_execution_service import run_owned_agent_goal

    result = run_owned_agent_goal(owner_id=7, goal="Review this safely")
    assert result == {"runtime": "legacy", "owner_id": 7}


def test_langgraph_unavailable_falls_back_before_execution(monkeypatch):
    monkeypatch.setenv("AI_LANGGRAPH_I19_ENABLED", "true")
    monkeypatch.setattr(
        "services.agent_execution_service.run_owned_agent_goal_legacy",
        lambda **kwargs: {"runtime": "legacy"},
    )
    import services.agent_langgraph_runtime_service as graph_service

    monkeypatch.setattr(graph_service, "StateGraph", None)
    monkeypatch.setattr(graph_service, "START", None)
    monkeypatch.setattr(graph_service, "END", None)

    from services.agent_execution_service import run_owned_agent_goal

    assert run_owned_agent_goal(owner_id=1, goal="Review this safely") == {"runtime": "legacy"}


def test_langgraph_i19_executes_existing_read_only_plan_without_workspace_mutation(
    app, user, monkeypatch
):
    pytest.importorskip("langgraph")
    monkeypatch.setenv("AI_LANGGRAPH_I19_ENABLED", "true")
    monkeypatch.setattr(
        "services.agent_langgraph_runtime_service.reason_over_agent_observations",
        _fake_reasoning,
    )

    from services.agent_execution_service import run_owned_agent_goal

    with app.app_context():
        project = _project(user)
        before_tasks = Task.query.filter_by(user_id=user).count()
        before_proposals = LifeOSActionProposal.query.filter_by(user_id=user).count()

        run = run_owned_agent_goal(
            owner_id=user,
            goal="Help me move this project forward and identify blockers.",
            selected_context={"type": "project", "id": project.id},
        )

        assert isinstance(run, LifeOSAgentRun)
        assert run.status == "succeeded"
        assert run.tool_calls >= 3
        assert run.provider_calls == 1
        assert run.output["orchestration"] == "langgraph"
        assert run.output["read_only"] is True
        assert run.output["workspace_mutation"] is False
        assert run.output["confirmation_boundary"] == "I9"
        assert Task.query.filter_by(user_id=user).count() == before_tasks
        assert LifeOSActionProposal.query.filter_by(user_id=user).count() == before_proposals


def test_langgraph_graph_state_contract_contains_no_raw_user_content():
    from services.agent_langgraph_runtime_service import _SafeGraphState

    # Regression guard: only these orchestration metadata keys should ever be
    # introduced into LangGraph state. Raw goal/evidence/prompt/answer fields
    # would be automatically traceable and are intentionally forbidden.
    keys = set(_SafeGraphState.__annotations__)
    assert "goal" not in keys
    assert "selected_context" not in keys
    assert "evidence" not in keys
    assert "observations" not in keys
    assert "prompt" not in keys
    assert "answer" not in keys
    assert {
        "phase", "run_id", "step_index", "step_count", "tool_calls",
        "provider_calls", "failed", "failure_code",
    }.issubset(keys)
