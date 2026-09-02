from __future__ import annotations

from database import db
from models import LifeOSAgentRun, Project
from services.agent_reasoning_service import AgentReasoningItem, AgentReasoningResult
from services.intelligence_ask_service import _looks_like_goal_request, ask_lifeos


def _project(owner_id: int, title: str = "Agentic Ask project") -> Project:
    row = Project(
        user_id=owner_id,
        title=title,
        status="In Progress",
        priority="High",
        progress=55,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _fake_reasoning(**kwargs):
    evidence = kwargs["evidence_catalog"]
    evidence_id = evidence[0]["id"]
    return AgentReasoningResult(
        answer="LifeOS found one verified blocker that should be handled before deployment.",
        claims=(AgentReasoningItem("A verified blocker exists.", (evidence_id,)),),
        recommendations=(AgentReasoningItem("Resolve the highest-ranked project priority first.", (evidence_id,)),),
        provider="test",
        model="test-model",
    )


def test_i19_complex_goal_is_planned_inside_ask_without_running_tools(app, user):
    with app.app_context():
        project = _project(user)
        before = LifeOSAgentRun.query.filter_by(user_id=user).count()
        result = ask_lifeos(
            query="Help me get this project ready for deployment.",
            owner_id=user,
            selected_context={"type": "project", "id": project.id},
        )
        after = LifeOSAgentRun.query.filter_by(user_id=user).count()

        assert result.status == "goal_plan_ready"
        assert result.response_mode == "goal_plan"
        assert result.goal_plan is not None
        assert result.goal_plan["scope"]["type"] == "project"
        assert result.goal_plan["scope"]["id"] == project.id
        assert len(result.goal_plan["steps"]) >= 3
        assert after == before


def test_i19_simple_ask_request_keeps_existing_non_goal_path(app, user):
    with app.app_context():
        result = ask_lifeos(query="Which tasks are overdue?", owner_id=user)
        assert result.response_mode != "goal_plan"
        assert result.status != "goal_plan_ready"
        assert result.goal_plan is None


def test_i19_goal_review_alias_runs_from_intelligence_boundary(app, client, user, monkeypatch):
    monkeypatch.setattr("services.agent_runtime_service.reason_over_agent_observations", _fake_reasoning)
    with app.app_context():
        project = _project(user, "Integrated Ask project")
        project_id = int(project.id)

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "StrongPass123!"},
    )
    assert login.status_code == 200

    planned = client.post(
        "/api/v1/intelligence/ask",
        json={
            "query": "Help me get this project ready for deployment.",
            "selected_context": {"type": "project", "id": project_id},
        },
    )
    assert planned.status_code == 200
    payload = planned.get_json()
    assert payload["status"] == "goal_plan_ready"
    assert payload["goal_plan"]["scope"]["id"] == project_id

    executed = client.post(
        "/api/v1/intelligence/goal-runs",
        json={
            "goal": "Help me get this project ready for deployment.",
            "selected_context": {"type": "project", "id": project_id},
        },
    )
    assert executed.status_code == 201
    run = executed.get_json()["run"]
    assert run["status"] == "succeeded"
    assert run["safety"]["workspace_mutation"] is False
    assert run["output"]["workspace_mutation"] is False
    assert isinstance(run["output"].get("goal_summary"), dict)
    assert run["output"]["goal_summary"]["status_label"]
    assert len(run["output"].get("action_suggestions") or []) <= 2

    details = client.get(f"/api/v1/intelligence/goal-runs/{run['id']}")
    assert details.status_code == 200
    assert details.get_json()["run"]["id"] == run["id"]


def test_i19_multi_part_objective_request_uses_goal_plan(app, user):
    with app.app_context():
        project = _project(user, "Goal detection project")
        result = ask_lifeos(
            query="Identify the biggest blockers, what should I focus on, and what should I do to move this project forward?",
            owner_id=user,
            selected_context={"type": "project", "id": project.id},
        )
        assert result.status == "goal_plan_ready"
        assert result.response_mode == "goal_plan"
        assert result.goal_plan is not None
        assert result.goal_plan["scope"]["id"] == project.id


def test_i19_goal_detection_does_not_double_count_deployment_filename_tokens():
    assert _looks_like_goal_request("Help me get this project ready for deployment.") is True
    assert _looks_like_goal_request("Which tasks came from Deployment_Plan.pdf?") is False


def test_i19_does_not_override_context_connections_route(app, user, monkeypatch):
    def planner_must_not_run(**_kwargs):
        raise AssertionError("I19 planner must not override the deterministic context-connections route.")

    monkeypatch.setattr("services.intelligence_ask_service.plan_owned_agent_goal", planner_must_not_run)
    with app.app_context():
        result = ask_lifeos(query="Which tasks came from Deployment_Plan.pdf?", owner_id=user)
        assert result.response_mode != "goal_plan"
        assert result.status != "goal_plan_ready"


def test_i19_context_connections_dispatches_before_goal_planner(monkeypatch):
    from types import SimpleNamespace

    fake_route = SimpleNamespace(
        intent="context_connections",
        scope_type=None,
        scope_id=None,
        scope_label=None,
        requires_clarification=False,
        clarification=None,
    )

    monkeypatch.setattr(
        "services.intelligence_ask_service.route_intelligence_request",
        lambda **_kwargs: fake_route,
    )
    monkeypatch.setattr(
        "services.intelligence_ask_service.plan_owned_agent_goal",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("planner must not run")),
    )
    fake_connections = SimpleNamespace(
        summary="One task came from Deployment_Plan.pdf.",
        connections=[{"kind": "task"}],
        to_dict=lambda: {"summary": "One task came from Deployment_Plan.pdf."},
    )
    monkeypatch.setattr(
        "services.intelligence_ask_service.query_owned_context_connections",
        lambda **_kwargs: fake_connections,
    )

    result = ask_lifeos(
        query="Which tasks came from Deployment_Plan.pdf?",
        owner_id=1,
    )
    assert result.response_mode == "deterministic_verified"
    assert result.status == "completed"
    assert result.answer == "One task came from Deployment_Plan.pdf."


def test_i19_explicit_project_goal_can_override_project_question_classification(app, user, monkeypatch):
    from dataclasses import replace
    from services.intelligence_intent_router_service import route_intelligence_request as real_router

    with app.app_context():
        project = _project(user, "Project-question precedence")
        baseline = real_router(
            query="Help me get this project ready for deployment.",
            owner_id=user,
            forced_project_id=project.id,
        )

        # Reproduce the compatibility edge explicitly: older router wording may
        # classify a goal-shaped request as a normal project question.  The
        # selected Project chip plus the goal detector must still hand this to I19.
        forced = replace(
            baseline,
            intent="project_question",
            scope_type="project",
            scope_id=project.id,
            scope_label=project.title,
            requires_clarification=False,
            clarification=None,
            candidates=(),
            status="ready",
        )
        monkeypatch.setattr(
            "services.intelligence_ask_service.route_intelligence_request",
            lambda **_kwargs: forced,
        )

        result = ask_lifeos(
            query="Help me get this project ready for deployment.",
            owner_id=user,
            selected_context={"type": "project", "id": project.id},
        )
        assert result.status == "goal_plan_ready"
        assert result.response_mode == "goal_plan"
        assert result.goal_plan is not None


def test_i19_explicit_project_does_not_turn_simple_project_question_into_goal(app, user):
    with app.app_context():
        project = _project(user, "Simple project question")
        result = ask_lifeos(
            query="How many tasks are overdue?",
            owner_id=user,
            selected_context={"type": "project", "id": project.id},
        )
        assert result.response_mode != "goal_plan"
        assert result.status != "goal_plan_ready"
