from __future__ import annotations

import pytest

from database import db
from models import Project
from services.automation_service import (
    AutomationValidationError,
    automation_registry,
    automation_to_dict,
    create_owned_automation,
    update_owned_automation,
    validate_visual_graph,
)


def _project(user_id: int, title: str = "LifeOS") -> Project:
    item = Project(user_id=user_id, title=title, status="In Progress", priority="Medium", progress=20)
    db.session.add(item)
    db.session.commit()
    return item


def _login(client):
    return client.post(
        "/login",
        data={"email": "student@example.com", "password": "StrongPass123!"},
        follow_redirects=False,
    )


def _legacy_graph(x: float = 70, y: float = 120):
    return {
        "version": 1,
        "nodes": [
            {"id": "trigger", "kind": "trigger", "position": {"x": x, "y": y}},
            {"id": "intelligence", "kind": "intelligence", "position": {"x": 380, "y": 140}},
            {"id": "delivery", "kind": "delivery", "position": {"x": 700, "y": 160}},
        ],
        "edges": [
            {"id": "a", "source": "trigger", "target": "intelligence"},
            {"id": "b", "source": "intelligence", "target": "delivery"},
        ],
    }


def _graph(*, trigger_type: str = "trigger.schedule_daily", action_type: str = "intelligence.today_briefing"):
    return {
        "version": 1,
        "phase": "I18.2",
        "nodes": [
            {"id": "start-node", "type": trigger_type, "category": "trigger", "position": {"x": 80, "y": 110}},
            {"id": "brain-node", "type": action_type, "category": "intelligence", "position": {"x": 410, "y": 150}},
            {"id": "notify-node", "type": "output.notify_me", "category": "output", "position": {"x": 760, "y": 170}},
        ],
        "edges": [
            {"id": "edge-a", "source": "start-node", "target": "brain-node"},
            {"id": "edge-b", "source": "brain-node", "target": "notify-node"},
        ],
    }


def test_i18_registry_exposes_registry_driven_builder_without_new_execution_runtime():
    registry = automation_registry()
    visual = registry["visual_flow"]
    assert visual["version"] == 1
    assert visual["phase"] == "I18.6"
    assert visual["node_order"] == ["trigger", "context", "intelligence", "condition", "output", "proposal"]
    assert visual["connections_fixed"] is False
    assert visual["layout_persisted"] is True
    assert visual["execution_source"] == "I17_allowlisted_trigger_and_action"
    assert visual["graph_is_execution_source"] is False
    assert visual["constraints"]["cycles_allowed"] is False
    assert visual["constraints"]["compiler_available"] is True
    assert any(node["type"] == "context.document" and node["availability"] == "i18_2" for node in visual["nodes"])
    assert any(node["type"] == "proposal.create_task" and node["confirmation_boundary"] == "I9" for node in visual["nodes"])
    assert registry["safety"]["workspace_mutation"] is False


def test_i18_visual_layout_and_user_node_ids_persist_while_i17_columns_remain_authoritative(app, user):
    with app.app_context():
        item = create_owned_automation(
            owner_id=user,
            name="Visual morning flow",
            trigger_type="schedule_daily",
            trigger_config={"hour": 8, "minute": 15},
            action_type="today_briefing",
            action_config={},
            timezone_name="UTC",
            visual_graph=_graph(),
        )
        payload = automation_to_dict(item)
        nodes = {node["id"]: node for node in payload["visual_graph"]["nodes"]}
        assert nodes["start-node"]["position"] == {"x": 80.0, "y": 110.0}
        assert nodes["start-node"]["type"] == "trigger.schedule_daily"
        assert nodes["start-node"]["config"] == {"hour": 8, "minute": 15}
        assert nodes["brain-node"]["semantic_type"] == "today_briefing"
        assert nodes["notify-node"]["semantic_type"] == "in_app_notification"
        assert payload["visual_graph"]["execution_binding"]["graph_is_execution_source"] is False
        assert payload["safety"]["workspace_mutation"] is False


def test_i18_upgrades_legacy_fixed_canvas_without_changing_execution_semantics():
    graph = validate_visual_graph(
        _legacy_graph(112, 99),
        trigger_type="schedule_daily",
        trigger_config={"hour": 9, "minute": 5},
        action_type="risk_escalation",
        action_config={},
    )
    nodes = {node["id"]: node for node in graph["nodes"]}
    assert nodes["trigger"]["type"] == "trigger.schedule_daily"
    assert nodes["trigger"]["position"] == {"x": 112.0, "y": 99.0}
    assert nodes["intelligence"]["type"] == "intelligence.detect_risks"
    assert nodes["delivery"]["type"] == "output.notify_me"
    assert graph["execution_binding"]["source"] == "I17_allowlisted_trigger_and_action"


def test_i18_rejects_future_nodes_rewired_edges_and_cycles():
    future = _graph()
    future["nodes"][1]["type"] = "context.document"
    future["nodes"][1]["category"] = "context"
    with pytest.raises(AutomationValidationError):
        validate_visual_graph(
            future,
            trigger_type="schedule_daily",
            trigger_config={"hour": 8, "minute": 0},
            action_type="today_briefing",
            action_config={},
        )

    rewired = _graph()
    rewired["edges"] = [
        {"id": "edge-a", "source": "start-node", "target": "notify-node"},
        {"id": "edge-b", "source": "notify-node", "target": "brain-node"},
    ]
    with pytest.raises(AutomationValidationError):
        validate_visual_graph(
            rewired,
            trigger_type="schedule_daily",
            trigger_config={"hour": 8, "minute": 0},
            action_type="today_briefing",
            action_config={},
        )

    legacy_cycle = _legacy_graph()
    legacy_cycle["edges"] = [
        {"id": "a", "source": "trigger", "target": "intelligence"},
        {"id": "b", "source": "intelligence", "target": "trigger"},
    ]
    with pytest.raises(AutomationValidationError):
        validate_visual_graph(
            legacy_cycle,
            trigger_type="schedule_daily",
            trigger_config={"hour": 8, "minute": 0},
            action_type="today_briefing",
            action_config={},
        )


def test_i18_rejects_graph_semantics_that_do_not_match_i17_binding():
    mismatched = _graph(action_type="intelligence.detect_risks")
    with pytest.raises(AutomationValidationError):
        validate_visual_graph(
            mismatched,
            trigger_type="schedule_daily",
            trigger_config={"hour": 8, "minute": 0},
            action_type="today_briefing",
            action_config={},
        )


def test_i18_editing_visual_flow_cannot_bypass_project_ownership(app, user):
    with app.app_context():
        owned = _project(user, "Owned")
        item = create_owned_automation(
            owner_id=user,
            name="Owned project review",
            trigger_type="schedule_weekly",
            trigger_config={"weekday": 0, "hour": 9, "minute": 0},
            action_type="project_review",
            action_config={"project_id": owned.id},
            timezone_name="UTC",
            visual_graph=_graph(trigger_type="trigger.schedule_weekly", action_type="intelligence.project_review"),
        )
        with pytest.raises(AutomationValidationError):
            update_owned_automation(
                owner_id=user,
                automation_id=item.id,
                payload={
                    "action_type": "project_review",
                    "action_config": {"project_id": owned.id + 99999},
                    "visual_graph": _graph(trigger_type="trigger.schedule_weekly", action_type="intelligence.project_review"),
                },
            )


def test_i18_api_accepts_and_returns_canonical_visual_graph(client, user):
    _login(client)
    created = client.post("/api/v1/automations", json={
        "name": "Canvas flow",
        "trigger_type": "schedule_daily",
        "trigger_config": {"hour": 10, "minute": 5},
        "action_type": "today_briefing",
        "action_config": {},
        "timezone": "UTC",
        "visual_graph": _graph(),
    })
    assert created.status_code == 201
    body = created.get_json()["automation"]
    assert body["visual_graph"]["version"] == 1
    assert body["visual_graph"]["phase"] == "I18.6"
    assert body["visual_graph"]["execution_binding"]["graph_is_execution_source"] is False

    automation_id = body["id"]
    changed = _graph()
    changed["nodes"][0]["position"] = {"x": 222, "y": 111}
    updated = client.patch(f"/api/v1/automations/{automation_id}", json={"visual_graph": changed})
    assert updated.status_code == 200
    nodes = {node["id"]: node for node in updated.get_json()["automation"]["visual_graph"]["nodes"]}
    assert nodes["start-node"]["position"] == {"x": 222.0, "y": 111.0}
