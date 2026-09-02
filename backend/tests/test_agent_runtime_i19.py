from __future__ import annotations

from pathlib import Path

import pytest

from database import db
from models import LifeOSActionProposal, LifeOSAgentRun, Project, Task, User
from services.agent_planner_service import plan_owned_agent_goal
from services.agent_reasoning_service import AgentReasoningItem, AgentReasoningResult
from services.agent_runtime_service import (
    AGENT_LIMITS,
    agent_registry_payload,
    prepare_agent_action_proposal,
    run_owned_agent_goal,
)
from services.ask_context_picker_service import AskContextNotFoundError
from services.intelligence_action_service import confirm_owned_action_proposal


def _project(owner_id: int, title: str = "I19 Agent Project") -> Project:
    row = Project(
        user_id=owner_id,
        title=title,
        status="In Progress",
        priority="High",
        progress=35,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _fake_reasoning(**kwargs):
    evidence = kwargs["evidence_catalog"]
    evidence_id = evidence[0]["id"]
    return AgentReasoningResult(
        answer="The project needs a concrete next action before it is ready.",
        claims=(AgentReasoningItem("The project has a current verified attention signal.", (evidence_id,)),),
        recommendations=(AgentReasoningItem("Review the top LifeOS priority and decide whether to turn it into a task.", (evidence_id,)),),
        provider="test",
        model="test-model",
    )


def test_i19_plan_is_goal_driven_bounded_and_read_only(app, user):
    with app.app_context():
        project = _project(user)
        plan = plan_owned_agent_goal(
            owner_id=user,
            goal="Help me get this project ready for deployment and find blockers.",
            selected_context={"type": "project", "id": project.id},
        )
        assert plan.scope.type == "project"
        assert 1 <= len(plan.steps) <= AGENT_LIMITS["max_steps"]
        names = [step.tool_name for step in plan.steps]
        assert "project.get_summary" in names
        assert "project.get_tasks" in names
        assert "project.review" in names
        assert "project.get_documents" in names
        assert all("create" not in name and "delete" not in name and "update" not in name for name in names)
        registry = agent_registry_payload()
        assert registry["safety"]["workspace_mutation"] is False
        assert all(item["mutates_state"] is False for item in registry["tools"])


def test_i19_planner_revalidates_selected_context_ownership(app, user):
    with app.app_context():
        other = User(name="Other", email="other-agent@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.commit()
        private = _project(other.id, "Other private project")
        with pytest.raises(AskContextNotFoundError):
            plan_owned_agent_goal(
                owner_id=user,
                goal="Review this project.",
                selected_context={"type": "project", "id": private.id},
            )


def test_i19_agent_run_executes_read_only_tools_and_persists_audit(app, user, monkeypatch):
    monkeypatch.setattr("services.agent_runtime_service.reason_over_agent_observations", _fake_reasoning)
    with app.app_context():
        project = _project(user)
        before_tasks = Task.query.filter_by(user_id=user).count()
        before_proposals = LifeOSActionProposal.query.filter_by(user_id=user).count()

        run = run_owned_agent_goal(
            owner_id=user,
            goal="Help me get this project ready for deployment.",
            selected_context={"type": "project", "id": project.id},
        )

        assert run.status == "succeeded"
        assert run.tool_calls >= 3
        assert run.provider_calls == 1
        assert run.output["answer"].startswith("The project needs")
        assert run.output["read_only"] is True
        assert run.output["workspace_mutation"] is False
        assert run.trace and all(step["status"] == "succeeded" for step in run.trace)
        assert LifeOSAgentRun.query.filter_by(id=run.id, user_id=user).count() == 1
        assert Task.query.filter_by(user_id=user).count() == before_tasks
        assert LifeOSActionProposal.query.filter_by(user_id=user).count() == before_proposals


def test_i19_action_suggestion_prepares_i9_proposal_and_only_confirm_mutates(app, user, monkeypatch):
    monkeypatch.setattr("services.agent_runtime_service.reason_over_agent_observations", _fake_reasoning)
    with app.app_context():
        project = _project(user)
        run = run_owned_agent_goal(
            owner_id=user,
            goal="Help me make concrete progress on this project.",
            selected_context={"type": "project", "id": project.id},
        )
        suggestions = run.output.get("action_suggestions") or []
        assert suggestions
        suggestion = suggestions[0]
        create_task_option = next((item for item in suggestion["options"] if item["type"] == "create_task"), None)
        assert create_task_option is not None

        before_tasks = Task.query.filter_by(user_id=user).count()
        proposal = prepare_agent_action_proposal(
            owner_id=user,
            run_id=run.id,
            suggestion_id=suggestion["id"],
            action_type="create_task",
        )
        assert proposal.status == "pending"
        assert proposal.requires_confirmation is True
        assert Task.query.filter_by(user_id=user).count() == before_tasks

        confirmed = confirm_owned_action_proposal(proposal_id=proposal.id, owner_id=user)
        assert confirmed.status == "confirmed"
        assert Task.query.filter_by(user_id=user).count() == before_tasks + 1


def test_i19_migration_extends_i18_head_linearly():
    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "20260831_0001_add_lifeos_agent_runs.py"
    text = path.read_text(encoding="utf-8")
    assert 'revision = "20260831_0001"' in text
    assert 'down_revision = "20260830_0002"' in text
    assert '"lifeos_agent_runs"' in text


def test_i19_api_plan_run_and_history_use_authenticated_owner(app, client, user, monkeypatch):
    monkeypatch.setattr("services.agent_runtime_service.reason_over_agent_observations", _fake_reasoning)
    with app.app_context():
        project = _project(user, "API Agent Project")
        project_id = int(project.id)

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "StrongPass123!"},
    )
    assert login.status_code == 200

    registry = client.get("/api/v1/agent/registry")
    assert registry.status_code == 200
    assert registry.get_json()["safety"]["workspace_mutation"] is False

    planned = client.post(
        "/api/v1/agent/plan",
        json={
            "goal": "Help me move this project forward.",
            "selected_context": {"type": "project", "id": project_id},
        },
    )
    assert planned.status_code == 200
    assert planned.get_json()["plan"]["scope"]["id"] == project_id

    executed = client.post(
        "/api/v1/agent/runs",
        json={
            "goal": "Help me move this project forward.",
            "selected_context": {"type": "project", "id": project_id},
        },
    )
    assert executed.status_code == 201
    run = executed.get_json()["run"]
    assert run["status"] == "succeeded"
    assert run["safety"]["workspace_mutation"] is False

    history = client.get("/api/v1/agent/runs")
    assert history.status_code == 200
    assert any(item["id"] == run["id"] for item in history.get_json()["runs"])
