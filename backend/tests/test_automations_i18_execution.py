from __future__ import annotations

import pytest

from database import db
from models import LifeOSActionProposal, LifeOSAutomationRun, Project
from services.automation_engine_service import execute_owned_automation
from services.automation_service import (
    AutomationValidationError,
    automation_registry,
    automation_to_dict,
    clear_owned_automation_error,
    create_owned_automation,
    preview_owned_automation,
    update_owned_automation,
)


def _project(user_id: int, title: str = "I18 Execution Project") -> Project:
    row = Project(user_id=user_id, title=title, status="In Progress", priority="High", progress=20)
    db.session.add(row)
    db.session.commit()
    return row


def _manual_review_graph():
    return {
        "version": 1,
        "phase": "I18.6",
        "nodes": [
            {"id": "trigger-1", "type": "trigger.manual_run", "category": "trigger", "position": {"x": 60, "y": 120}, "config": {}},
            {"id": "review-1", "type": "intelligence.portfolio_review", "category": "intelligence", "position": {"x": 360, "y": 120}, "config": {}},
            {"id": "changed-1", "type": "intelligence.what_changed", "category": "intelligence", "position": {"x": 660, "y": 120}, "config": {}},
            {"id": "save-1", "type": "output.save_review_result", "category": "output", "position": {"x": 960, "y": 120}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "trigger-1", "target": "review-1"},
            {"id": "e2", "source": "review-1", "target": "changed-1"},
            {"id": "e3", "source": "changed-1", "target": "save-1"},
        ],
    }


def _proposal_graph():
    return {
        "version": 1,
        "phase": "I18.6",
        "nodes": [
            {"id": "trigger-1", "type": "trigger.manual_run", "category": "trigger", "position": {"x": 60, "y": 120}, "config": {}},
            {"id": "review-1", "type": "intelligence.portfolio_review", "category": "intelligence", "position": {"x": 360, "y": 120}, "config": {}},
            {"id": "suggest-1", "type": "output.suggest_action", "category": "output", "position": {"x": 660, "y": 120}, "config": {}},
            {"id": "proposal-1", "type": "proposal.create_task", "category": "proposal", "position": {"x": 960, "y": 120}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "trigger-1", "target": "review-1"},
            {"id": "e2", "source": "review-1", "target": "suggest-1"},
            {"id": "e3", "source": "suggest-1", "target": "proposal-1"},
        ],
    }


def _direct_proposal_graph():
    return {
        "version": 1,
        "phase": "I18.6",
        "nodes": [
            {"id": "trigger-1", "type": "trigger.manual_run", "category": "trigger", "position": {"x": 60, "y": 120}, "config": {}},
            {"id": "review-1", "type": "intelligence.portfolio_review", "category": "intelligence", "position": {"x": 360, "y": 120}, "config": {}},
            {"id": "proposal-1", "type": "proposal.save_note", "category": "proposal", "position": {"x": 660, "y": 120}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "trigger-1", "target": "review-1"},
            {"id": "e2", "source": "review-1", "target": "proposal-1"},
        ],
    }


def _failing_manual_event_graph():
    return {
        "version": 1,
        "phase": "I18.6",
        "nodes": [
            {"id": "trigger-1", "type": "trigger.manual_run", "category": "trigger", "position": {"x": 60, "y": 120}, "config": {}},
            {"id": "event-1", "type": "intelligence.event_context_review", "category": "intelligence", "position": {"x": 360, "y": 120}, "config": {}},
            {"id": "save-1", "type": "output.save_review_result", "category": "output", "position": {"x": 660, "y": 120}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "trigger-1", "target": "event-1"},
            {"id": "e2", "source": "event-1", "target": "save-1"},
        ],
    }


def test_i18_6_registry_marks_rich_execution_and_templates_live():
    registry = automation_registry()
    visual = registry["visual_flow"]
    assert visual["phase"] == "I18.6"
    assert visual["constraints"]["rich_graph_execution_available"] is True
    assert visual["constraints"]["branching_allowed"] is False
    assert any(node["type"] == "trigger.manual_run" and node["availability"] == "i18_6" for node in visual["nodes"])
    assert len(registry["visual_templates"]) >= 3


def test_i18_6_manual_compiled_flow_runs_but_cannot_be_background_enabled(app, user):
    with app.app_context():
        _project(user)
        item = create_owned_automation(
            owner_id=user,
            name="Manual compiled review",
            enabled=False,
            trigger_type="manual",
            trigger_config={},
            action_type="portfolio_review",
            action_config={},
            timezone_name="UTC",
            visual_graph=_manual_review_graph(),
        )
        payload = automation_to_dict(item)
        assert payload["execution"]["mode"] == "compiled_i17"
        assert payload["execution"]["run_now_available"] is True
        assert payload["execution"]["background_available"] is False
        assert payload["next_run_at"] is None

        execution = execute_owned_automation(owner_id=user, automation_id=item.id)
        assert execution.output["workspace_mutation"] is False
        assert [step["status"] for step in execution.output["flow_trace"]] == ["succeeded"] * 4

        with pytest.raises(AutomationValidationError):
            update_owned_automation(owner_id=user, automation_id=item.id, payload={"enabled": True})


def test_i18_6_preview_never_persists_i9_proposal(app, user):
    with app.app_context():
        _project(user, "Proposal project")
        item = create_owned_automation(
            owner_id=user,
            name="Proposal preview flow",
            enabled=False,
            trigger_type="manual",
            trigger_config={},
            action_type="portfolio_review",
            action_config={},
            timezone_name="UTC",
            visual_graph=_proposal_graph(),
        )
        before = LifeOSActionProposal.query.filter_by(user_id=user).count()
        preview = preview_owned_automation(owner_id=user, automation_id=item.id)
        after = LifeOSActionProposal.query.filter_by(user_id=user).count()
        assert after == before
        assert preview.output["workspace_mutation"] is False
        assert preview.output["dry_run"] is True
        proposal = preview.output.get("proposal")
        if proposal is not None:
            assert proposal["status"] == "preview"
            assert proposal["requires_confirmation"] is True


def test_i18_5_failed_node_trace_is_preserved_and_clear_error_keeps_history(app, user):
    with app.app_context():
        item = create_owned_automation(
            owner_id=user,
            name="Failure evidence flow",
            enabled=False,
            trigger_type="manual",
            trigger_config={},
            action_type="attention_notice",
            action_config={},
            timezone_name="UTC",
            visual_graph=_failing_manual_event_graph(),
        )
        with pytest.raises(Exception):
            execute_owned_automation(owner_id=user, automation_id=item.id)

        run = LifeOSAutomationRun.query.filter_by(user_id=user, automation_id=item.id).order_by(LifeOSAutomationRun.id.desc()).first()
        assert run is not None
        assert run.status == "failed"
        assert run.output["failed_node_id"] == "event-1"
        assert any(step["node_id"] == "event-1" and step["status"] == "failed" for step in run.output["flow_trace"])
        run_id = run.id

        cleared = clear_owned_automation_error(owner_id=user, automation_id=item.id)
        assert cleared.status == "ready"
        assert LifeOSAutomationRun.query.filter_by(id=run_id, user_id=user).first() is not None


def test_i18_ux_direct_ask_me_first_preview_is_safe_and_does_not_require_output(app, user):
    with app.app_context():
        item = create_owned_automation(
            owner_id=user,
            name="Direct approval terminal",
            trigger_type="manual_run",
            trigger_config={},
            action_type="portfolio_review",
            action_config={},
            timezone_name="UTC",
            visual_graph=_direct_proposal_graph(),
        )
        before = LifeOSActionProposal.query.filter_by(user_id=user).count()
        preview = preview_owned_automation(owner_id=user, automation_id=item.id)
        after = LifeOSActionProposal.query.filter_by(user_id=user).count()
        assert after == before
        assert preview.status == "preview"
        trace = preview.output.get("visual_flow", {}).get("node_runs", [])
        assert trace[-1]["capability"] == "proposal.save_note"
        assert trace[-1]["status"] == "succeeded"


class _FakeAskResult:
    def __init__(self, answer: str | None):
        self.answer = answer

    def to_dict(self, *, include_diagnostics: bool = False):
        return {
            "answer": self.answer,
            "clarification": None,
            "attention_level": None,
            "verification": {"status": "verified"},
            "grounded": None,
            "response_mode": "deterministic_verified",
        }


def _custom_question_graph(*, project_id: int | None = None, with_gate: bool = False):
    nodes = [
        {"id": "trigger-1", "type": "trigger.manual_run", "category": "trigger", "position": {"x": 60, "y": 120}, "config": {}},
    ]
    edges = []
    previous = "trigger-1"
    if project_id is not None:
        nodes.append({"id": "context-1", "type": "context.project", "category": "context", "position": {"x": 330, "y": 120}, "config": {"scope_mode": "selected", "project_id": project_id}})
        edges.append({"id": "e1", "source": previous, "target": "context-1"})
        previous = "context-1"
    nodes.append({"id": "ask-1", "type": "intelligence.ask_lifeos", "category": "intelligence", "position": {"x": 600, "y": 120}, "config": {"instruction": "What needs my attention next?"}})
    edges.append({"id": f"e{len(edges) + 1}", "source": previous, "target": "ask-1"})
    previous = "ask-1"
    if with_gate:
        nodes.append({"id": "gate-1", "type": "condition.results_found", "category": "condition", "position": {"x": 860, "y": 120}, "config": {}})
        edges.append({"id": f"e{len(edges) + 1}", "source": previous, "target": "gate-1"})
        previous = "gate-1"
    nodes.append({"id": "output-1", "type": "output.notify_me", "category": "output", "position": {"x": 1120, "y": 120}, "config": {}})
    edges.append({"id": f"e{len(edges) + 1}", "source": previous, "target": "output-1"})
    return {"version": 1, "phase": "I18.6", "nodes": nodes, "edges": edges}


def test_i18_custom_ask_uses_selected_owned_context_and_stays_read_only(app, user, monkeypatch):
    captured = {}

    def fake_ask_lifeos(*, query, owner_id, selected_context=None, verification_policy="full", **_kwargs):
        captured["query"] = query
        captured["owner_id"] = owner_id
        captured["selected_context"] = selected_context
        captured["verification_policy"] = verification_policy
        return _FakeAskResult("Deployment testing is the strongest next focus.")

    monkeypatch.setattr("services.automation_flow_execution_service.ask_lifeos", fake_ask_lifeos)

    with app.app_context():
        project = _project(user, "Custom Ask Project")
        project_id = int(project.id)
        item = create_owned_automation(
            owner_id=user,
            name="Custom project question",
            enabled=False,
            trigger_type="manual",
            trigger_config={},
            action_type="custom_ask",
            action_config={"instruction": "What needs my attention next?"},
            timezone_name="UTC",
            visual_graph=_custom_question_graph(project_id=project_id),
        )
        execution = execute_owned_automation(owner_id=user, automation_id=item.id)
        assert captured["selected_context"] == {"type": "project", "id": project_id}
        assert captured["owner_id"] == user
        assert captured["verification_policy"] == "automation_fast"
        assert execution.output["workspace_mutation"] is False
        assert execution.output["answer"] == "Deployment testing is the strongest next focus."
        assert any(step["capability"] == "intelligence.ask_lifeos" and step["status"] == "succeeded" for step in execution.output["flow_trace"])


def test_i18_condition_gate_stops_quietly_and_skips_later_steps(app, user, monkeypatch):
    def fake_ask_lifeos(**_kwargs):
        return _FakeAskResult(None)

    monkeypatch.setattr("services.automation_flow_execution_service.ask_lifeos", fake_ask_lifeos)

    with app.app_context():
        item = create_owned_automation(
            owner_id=user,
            name="Quiet no-result gate",
            enabled=False,
            trigger_type="manual",
            trigger_config={},
            action_type="custom_ask",
            action_config={"instruction": "Find anything that needs attention."},
            timezone_name="UTC",
            visual_graph=_custom_question_graph(with_gate=True),
        )
        execution = execute_owned_automation(owner_id=user, automation_id=item.id)
        assert execution.output["flow_halted"] is True
        assert execution.output["workspace_mutation"] is False
        assert "ended this run quietly" in str(execution.output["halt_reason"])
        trace = execution.output["flow_trace"]
        assert next(step for step in trace if step["node_id"] == "gate-1")["status"] == "succeeded"
        assert next(step for step in trace if step["node_id"] == "gate-1")["result"]["condition_passed"] is False
        assert next(step for step in trace if step["node_id"] == "output-1")["status"] == "skipped"
        assert execution.output.get("notification") is None


def test_i18_registry_exposes_safe_condition_gates_and_custom_ask():
    registry = automation_registry()
    node_types = {node["type"] for node in registry["visual_flow"]["nodes"]}
    assert "intelligence.ask_lifeos" in node_types
    assert "condition.attention_needed" in node_types
    assert "condition.results_found" in node_types
    assert {"source": "intelligence", "target": "condition"} in registry["visual_flow"]["connection_rules"]
    assert {"source": "condition", "target": "output"} in registry["visual_flow"]["connection_rules"]
    assert registry["safety"]["workspace_mutation"] is False


def test_i18_project_review_result_is_reused_by_detect_risks(app, user, monkeypatch):
    calls = {"count": 0}

    def fake_project_review_output(*, owner_id, project_id):
        calls["count"] += 1
        return {
            "kind": "project_review",
            "project_id": int(project_id),
            "title": "Project review ready",
            "summary": "One high risk was found.",
            "attention_level": "high",
            "priorities": [{"title": "Deployment blocker", "severity": "high", "project_id": int(project_id)}],
            "priority_count": 1,
            "verified_from_state": True,
            "read_only": True,
        }

    monkeypatch.setattr("services.automation_flow_execution_service._project_review_output", fake_project_review_output)

    with app.app_context():
        project = _project(user, "Reuse Project")
        project_id = int(project.id)
        graph = {
            "version": 1,
            "phase": "I18.6",
            "nodes": [
                {"id": "trigger-1", "type": "trigger.manual_run", "category": "trigger", "position": {"x": 60, "y": 120}, "config": {}},
                {"id": "context-1", "type": "context.project", "category": "context", "position": {"x": 330, "y": 120}, "config": {"scope_mode": "selected", "project_id": project_id}},
                {"id": "review-1", "type": "intelligence.project_review", "category": "intelligence", "position": {"x": 600, "y": 120}, "config": {"project_id": project_id}},
                {"id": "risk-1", "type": "intelligence.detect_risks", "category": "intelligence", "position": {"x": 860, "y": 120}, "config": {}},
                {"id": "output-1", "type": "output.save_review_result", "category": "output", "position": {"x": 1120, "y": 120}, "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "trigger-1", "target": "context-1"},
                {"id": "e2", "source": "context-1", "target": "review-1"},
                {"id": "e3", "source": "review-1", "target": "risk-1"},
                {"id": "e4", "source": "risk-1", "target": "output-1"},
            ],
        }
        item = create_owned_automation(
            owner_id=user,
            name="Reuse intelligence output",
            enabled=False,
            trigger_type="manual",
            trigger_config={},
            action_type="project_review",
            action_config={"project_id": project_id},
            timezone_name="UTC",
            visual_graph=graph,
        )
        execution = execute_owned_automation(owner_id=user, automation_id=item.id)
        assert calls["count"] == 1
        risk_step = next(step for step in execution.output["flow_trace"] if step["node_id"] == "risk-1")
        assert risk_step["result"]["reused_previous_step"] is True
        assert risk_step["input_from_node_id"] == "review-1"


def test_i18_custom_ask_can_prepare_note_proposal_from_its_own_verified_result(app, user, monkeypatch):
    def fake_ask_lifeos(**_kwargs):
        return _FakeAskResult("The deployment checklist still needs a rollback verification note.")

    monkeypatch.setattr("services.automation_flow_execution_service.ask_lifeos", fake_ask_lifeos)

    with app.app_context():
        project = _project(user, "Proposal From Result Project")
        project_id = int(project.id)
        graph = _custom_question_graph(project_id=project_id)
        graph["nodes"][-1] = {"id": "proposal-1", "type": "proposal.save_note", "category": "proposal", "position": {"x": 1120, "y": 120}, "config": {}}
        graph["edges"][-1] = {"id": graph["edges"][-1]["id"], "source": "ask-1", "target": "proposal-1"}
        item = create_owned_automation(
            owner_id=user,
            name="Save custom answer safely",
            enabled=False,
            trigger_type="manual",
            trigger_config={},
            action_type="custom_ask",
            action_config={"instruction": "What verified deployment insight should I keep?"},
            timezone_name="UTC",
            visual_graph=graph,
        )
        before = LifeOSActionProposal.query.filter_by(user_id=user).count()
        preview = preview_owned_automation(owner_id=user, automation_id=item.id)
        after = LifeOSActionProposal.query.filter_by(user_id=user).count()
        assert after == before
        assert preview.output["proposal"]["action_type"] == "create_note"
        assert preview.output["proposal"]["project_id"] == project_id
        assert preview.output["proposal"]["requires_confirmation"] is True


def test_i18_passing_condition_preserves_intelligence_result_for_output(app, user, monkeypatch):
    def fake_ask_lifeos(**_kwargs):
        return _FakeAskResult("A verified blocker was found.")

    monkeypatch.setattr("services.automation_flow_execution_service.ask_lifeos", fake_ask_lifeos)

    with app.app_context():
        item = create_owned_automation(
            owner_id=user,
            name="Gate preserves result",
            enabled=False,
            trigger_type="manual",
            trigger_config={},
            action_type="custom_ask",
            action_config={"instruction": "Find blockers."},
            timezone_name="UTC",
            visual_graph=_custom_question_graph(with_gate=True),
        )
        execution = execute_owned_automation(owner_id=user, automation_id=item.id)
        assert execution.output["flow_halted"] is False
        assert execution.output["answer"] == "A verified blocker was found."
        assert execution.output["notification"]["should_notify"] is True
        gate = next(step for step in execution.output["flow_trace"] if step["node_id"] == "gate-1")
        assert gate["result"]["condition_passed"] is True


def test_i18_common_project_risk_question_uses_fast_verified_agent_path(app, user, monkeypatch):
    """Common blocker/risk questions should not spend a provider call in I18."""

    def provider_should_not_run(**_kwargs):
        raise AssertionError("The deterministic project-risk fast path should answer this automation question.")

    monkeypatch.setattr("services.automation_flow_execution_service.ask_lifeos", provider_should_not_run)

    with app.app_context():
        project = _project(user, "Fast Risk Project")
        project_id = int(project.id)
        graph = _custom_question_graph(project_id=project_id)
        ask_node = next(node for node in graph["nodes"] if node["id"] == "ask-1")
        ask_node["config"] = {"instruction": "What is the biggest unresolved issue that could delay this project?"}
        item = create_owned_automation(
            owner_id=user,
            name="Fast project blocker check",
            enabled=False,
            trigger_type="manual",
            trigger_config={},
            action_type="custom_ask",
            action_config={"instruction": ask_node["config"]["instruction"]},
            timezone_name="UTC",
            visual_graph=graph,
        )

        execution = execute_owned_automation(owner_id=user, automation_id=item.id)
        ask_step = next(step for step in execution.output["flow_trace"] if step["node_id"] == "ask-1")
        assert ask_step["status"] == "succeeded"
        assert ask_step["result"]["response_mode"] == "agent_verified_fast"
        assert ask_step["result"]["ai_provider_calls"] == 0
        assert execution.output["workspace_mutation"] is False
