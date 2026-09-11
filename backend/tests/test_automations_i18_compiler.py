from __future__ import annotations

import pytest

from database import db
from models import LifeOSAutomation, Project, User
from services.automation_engine_service import execute_owned_automation
from services.automation_service import (
    AutomationValidationError,
    automation_registry,
    automation_to_dict,
    compile_owned_visual_flow_draft,
    create_owned_automation,
    update_owned_automation,
)


def _project(user_id: int, title: str = "Compiler Project") -> Project:
    item = Project(user_id=user_id, title=title, status="In Progress", priority="Medium", progress=30)
    db.session.add(item)
    db.session.commit()
    return item


def _complex_graph(project_id: int):
    return {
        "version": 1,
        "phase": "I18.2",
        "nodes": [
            {"id": "trigger-1", "type": "trigger.schedule_daily", "category": "trigger", "position": {"x": 60, "y": 120}, "config": {"hour": 8, "minute": 0}},
            {"id": "context-1", "type": "context.project", "category": "context", "position": {"x": 340, "y": 120}, "config": {"scope_mode": "selected", "project_id": project_id}},
            {"id": "rank-1", "type": "intelligence.rank_priorities", "category": "intelligence", "position": {"x": 620, "y": 120}, "config": {}},
            {"id": "brief-1", "type": "intelligence.today_briefing", "category": "intelligence", "position": {"x": 900, "y": 120}, "config": {}},
            {"id": "notify-1", "type": "output.notify_me", "category": "output", "position": {"x": 1180, "y": 120}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "trigger-1", "target": "context-1"},
            {"id": "e2", "source": "context-1", "target": "rank-1"},
            {"id": "e3", "source": "rank-1", "target": "brief-1"},
            {"id": "e4", "source": "brief-1", "target": "notify-1"},
        ],
    }


def _proposal_graph():
    return {
        "version": 1,
        "phase": "I18.2",
        "nodes": [
            {"id": "trigger-1", "type": "trigger.schedule_weekly", "category": "trigger", "position": {"x": 60, "y": 120}, "config": {"weekday": 6, "hour": 18, "minute": 0}},
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


def test_i18_2_registry_exposes_constrained_compiler_and_keeps_i17_runtime_authoritative():
    visual = automation_registry()["visual_flow"]
    assert visual["phase"] == "I18.6"
    assert visual["constraints"]["compiler_available"] is True
    assert visual["constraints"]["branching_allowed"] is False
    assert visual["constraints"]["cycles_allowed"] is False
    assert visual["constraints"]["rich_graph_execution_available"] is True
    assert visual["execution_source"] == "I17_allowlisted_trigger_and_action"
    assert visual["graph_is_execution_source"] is False
    assert visual["compiler_is_execution_source"] is True
    assert any(node["type"] == "context.document" and node["availability"] == "i18_2" for node in visual["nodes"])
    assert any(node["type"] == "proposal.create_task" and node["confirmation_boundary"] == "I9" for node in visual["nodes"])


def test_i18_2_compiles_rich_graph_deterministically_but_does_not_execute_it(app, user):
    with app.app_context():
        project = _project(user)
        result = compile_owned_visual_flow_draft(
            owner_id=user,
            trigger_type="schedule_daily",
            trigger_config={"hour": 8, "minute": 0},
            action_type="today_briefing",
            action_config={},
            visual_graph=_complex_graph(project.id),
        )
        plan = result["compiled_plan"]
        assert plan["phase"] == "I18.6"
        assert plan["execution"]["mode"] == "compiled_i17"
        assert plan["execution"]["run_now_available"] is True
        assert plan["execution"]["background_available"] is True
        assert plan["i17_binding"]["storage_anchor_only"] is True
        assert plan["ordered_node_ids"] == ["trigger-1", "context-1", "rank-1", "brief-1", "notify-1"]
        assert [step["capability"] for step in plan["steps"]] == [
            "schedule.daily",
            "context.project",
            "intelligence.rank_priorities",
            "intelligence.today_briefing",
            "output.notify_me",
        ]
        assert result["visual_graph"]["execution_binding"]["i17_anchor_node_id"] == "brief-1"

        again = compile_owned_visual_flow_draft(
            owner_id=user,
            trigger_type="schedule_daily",
            trigger_config={"hour": 8, "minute": 0},
            action_type="today_briefing",
            action_config={},
            visual_graph=_complex_graph(project.id),
        )
        assert again["compiled_plan"]["plan_id"] == plan["plan_id"]


def test_i18_2_rich_graph_cannot_enable_preview_or_run_before_execution_phase(app, user):
    with app.app_context():
        project = _project(user)
        item = create_owned_automation(
            owner_id=user,
            name="Compiled morning flow",
            enabled=False,
            trigger_type="schedule_daily",
            trigger_config={"hour": 8, "minute": 0},
            action_type="today_briefing",
            action_config={},
            timezone_name="UTC",
            visual_graph=_complex_graph(project.id),
        )
        payload = automation_to_dict(item)
        assert payload["status"] == "ready"
        assert payload["execution"]["run_now_available"] is True
        assert payload["execution"]["background_available"] is True
        assert payload["next_run_at"] is not None

        result = execute_owned_automation(owner_id=user, automation_id=item.id)
        assert result.output["workspace_mutation"] is False
        assert len(result.output["flow_trace"]) == 5
        updated = update_owned_automation(owner_id=user, automation_id=item.id, payload={"enabled": True})
        assert updated.enabled is True



def test_i18_2_rejects_unregistered_nodes_and_branching(app, user):
    with app.app_context():
        project = _project(user, "Validation project")
        unknown = _complex_graph(project.id)
        unknown["nodes"][2]["type"] = "intelligence.execute_sql"
        with pytest.raises(AutomationValidationError):
            compile_owned_visual_flow_draft(
                owner_id=user,
                trigger_type="schedule_daily",
                trigger_config={"hour": 8, "minute": 0},
                action_type="today_briefing",
                action_config={},
                visual_graph=unknown,
            )

        branched = _complex_graph(project.id)
        branched["edges"] = [
            {"id": "e1", "source": "trigger-1", "target": "context-1"},
            {"id": "e2", "source": "context-1", "target": "rank-1"},
            {"id": "e3", "source": "context-1", "target": "brief-1"},
            {"id": "e4", "source": "brief-1", "target": "notify-1"},
        ]
        with pytest.raises(AutomationValidationError):
            compile_owned_visual_flow_draft(
                owner_id=user,
                trigger_type="schedule_daily",
                trigger_config={"hour": 8, "minute": 0},
                action_type="today_briefing",
                action_config={},
                visual_graph=branched,
            )

def test_i18_2_context_ownership_is_backend_enforced(app, user):
    with app.app_context():
        other_user = User(name="Other owner", email="other-automation-owner@example.com")
        other_user.set_password("StrongPass123!")
        db.session.add(other_user)
        db.session.commit()
        other = _project(other_user.id, "Other owner")
        with pytest.raises(AutomationValidationError):
            compile_owned_visual_flow_draft(
                owner_id=user,
                trigger_type="schedule_daily",
                trigger_config={"hour": 8, "minute": 0},
                action_type="today_briefing",
                action_config={},
                visual_graph=_complex_graph(other.id),
            )


def test_i18_2_i9_proposal_compiles_with_legacy_suggest_action_path(app, user):
    with app.app_context():
        result = compile_owned_visual_flow_draft(
            owner_id=user,
            trigger_type="schedule_weekly",
            trigger_config={"weekday": 6, "hour": 18, "minute": 0},
            action_type="portfolio_review",
            action_config={},
            visual_graph=_proposal_graph(),
        )
        proposal = result["compiled_plan"]["steps"][-1]
        assert proposal["capability"] == "proposal.create_task"
        assert proposal["confirmation_boundary"] == "I9"
        assert proposal["proposal_only"] is True
        assert proposal["workspace_mutation"] is False
        assert result["compiled_plan"]["safety"]["important_workspace_actions_require"] == "I9_confirmation"

        invalid = _proposal_graph()
        invalid["nodes"][2]["type"] = "output.notify_me"
        with pytest.raises(AutomationValidationError):
            compile_owned_visual_flow_draft(
                owner_id=user,
                trigger_type="schedule_weekly",
                trigger_config={"weekday": 6, "hour": 18, "minute": 0},
                action_type="portfolio_review",
                action_config={},
                visual_graph=invalid,
            )


def test_i18_ux_ask_me_first_can_be_the_terminal_then_without_redundant_output(app, user):
    graph = {
        "version": 1,
        "phase": "I18.6",
        "nodes": [
            {"id": "trigger-1", "type": "trigger.schedule_weekly", "category": "trigger", "position": {"x": 60, "y": 120}, "config": {"weekday": 6, "hour": 18, "minute": 0}},
            {"id": "review-1", "type": "intelligence.portfolio_review", "category": "intelligence", "position": {"x": 360, "y": 120}, "config": {}},
            {"id": "proposal-1", "type": "proposal.save_note", "category": "proposal", "position": {"x": 660, "y": 120}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "trigger-1", "target": "review-1"},
            {"id": "e2", "source": "review-1", "target": "proposal-1"},
        ],
    }
    with app.app_context():
        result = compile_owned_visual_flow_draft(
            owner_id=user,
            trigger_type="schedule_weekly",
            trigger_config={"weekday": 6, "hour": 18, "minute": 0},
            action_type="portfolio_review",
            action_config={},
            visual_graph=graph,
        )
        steps = result["compiled_plan"]["steps"]
        assert [step["category"] for step in steps] == ["trigger", "intelligence", "proposal"]
        assert steps[-1]["capability"] == "proposal.save_note"
        assert steps[-1]["confirmation_boundary"] == "I9"
        assert steps[-1]["workspace_mutation"] is False


def _login(client):
    return client.post(
        "/login",
        data={"email": "student@example.com", "password": "StrongPass123!"},
        follow_redirects=False,
    )


def test_i18_2_compile_api_validates_without_persisting_or_executing(app, client, user):
    with app.app_context():
        project = _project(user, "Compile API project")
        project_id = project.id
        before = LifeOSAutomation.query.filter_by(user_id=user).count()

    _login(client)
    response = client.post("/api/v1/automations/compile", json={
        "trigger_type": "schedule_daily",
        "trigger_config": {"hour": 8, "minute": 0},
        "action_type": "today_briefing",
        "action_config": {},
        "visual_graph": _complex_graph(project_id),
    })
    assert response.status_code == 200
    body = response.get_json()
    assert body["compiled_plan"]["execution"]["mode"] == "compiled_i17"
    assert body["compiled_plan"]["execution"]["run_now_available"] is True
    assert body["compiled_plan"]["safety"]["workspace_mutation"] is False

    with app.app_context():
        assert LifeOSAutomation.query.filter_by(user_id=user).count() == before
