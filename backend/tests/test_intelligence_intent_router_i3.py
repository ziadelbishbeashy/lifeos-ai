from __future__ import annotations

from database import db
from models import Project, User
from services.intelligence_intent_router_service import route_intelligence_request
from services.intelligence_request_service import handle_intelligence_request


def _project(user_id: int, title: str) -> Project:
    project = Project(user_id=user_id, title=title, status="In Progress", priority="Medium")
    db.session.add(project)
    db.session.commit()
    return project


def _login(client):
    return client.post(
        "/login",
        data={"email": "student@example.com", "password": "StrongPass123!"},
        follow_redirects=False,
    )


def test_i3_routes_natural_project_review_to_owned_project(app, user):
    with app.app_context():
        project = _project(user, "LifeOS")
        decision = route_intelligence_request(
            query="How is my LifeOS project going?",
            owner_id=user,
        )
        assert decision.intent == "project_review"
        assert decision.scope_type == "project"
        assert decision.scope_id == project.id
        assert decision.scope_label == "LifeOS"
        assert decision.status == "ready"
        assert decision.requires_clarification is False


def test_i3_executes_only_reviewed_project_focus_workflow(app, user):
    """Attention wording now belongs to the reviewed I8 focus-agent contract.

    I3 originally treated this sentence as a passive project review. I8 later
    intentionally upgraded "what needs attention" to project_focus so the
    constrained review agent can rank priorities. Keep the older test aligned
    with the current product behavior instead of forcing the router backwards.
    """

    with app.app_context():
        project = _project(user, "LifeOS")
        result = handle_intelligence_request(
            query="Review my LifeOS project and tell me what needs attention",
            owner_id=user,
        ).to_dict()

        assert result["route"]["intent"] == "project_focus"
        assert result["result_type"] == "project_review_agent"
        assert result["result"]["kind"] == "project_review_agent"
        assert result["result"]["project_id"] == project.id
        assert result["result"]["read_only"] is True


def test_i3_task_status_intent_is_now_connected_to_i11_verified_executor(app, user):
    """I11 upgrades the previously route-only task_status intent."""
    with app.app_context():
        _project(user, "LifeOS")
        result = handle_intelligence_request(
            query="Which tasks are overdue?",
            owner_id=user,
        ).to_dict()
        assert result["route"]["intent"] == "task_status"
        assert result["result_type"] == "workspace_insight"
        assert result["result"]["kind"] == "overdue_tasks"
        assert result["result"]["verified_from_state"] is True
        assert result["read_only"] is True


def test_i3_does_not_resolve_another_users_project_id(app, user):
    with app.app_context():
        _project(user, "Owned Project")
        other = User(name="Other", email="i3-other@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.commit()
        hidden = _project(other.id, "Private Hidden Project")

        decision = route_intelligence_request(
            query=f"Review project {hidden.id}",
            owner_id=user,
        )
        payload = decision.to_dict()
        assert payload["scope"] is None
        assert payload["requires_clarification"] is True
        assert "Private Hidden Project" not in str(payload)


def test_i3_asks_for_clarification_instead_of_guessing_ambiguous_project(app, user):
    with app.app_context():
        _project(user, "LifeOS Web")
        _project(user, "LifeOS Mobile")
        decision = route_intelligence_request(
            query="How is my LifeOS project going?",
            owner_id=user,
        )
        assert decision.requires_clarification is True
        assert decision.status == "clarification_required"
        assert decision.scope_id is None


def test_i3_api_routes_request_without_exposing_internal_tool_data(client, app, user):
    with app.app_context():
        project = _project(user, "LifeOS")
        project_id = project.id

    _login(client)
    response = client.post(
        "/api/v1/intelligence/route",
        json={"query": "How is my LifeOS project going?"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["route"]["scope"]["id"] == project_id
    assert payload["result_type"] == "project_review"
    serialized = str(payload).lower()
    assert "tool_data" not in serialized
    assert "chunk_id" not in serialized
    assert "embedding" not in serialized
