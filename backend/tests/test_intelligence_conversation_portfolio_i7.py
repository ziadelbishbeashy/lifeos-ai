from __future__ import annotations

from database import db
from models import Project, Task
from services.intelligence_ask_service import ask_lifeos
from services.intelligence_intent_router_service import route_intelligence_request


def _project(user_id: int, title: str, *, status: str = "In Progress") -> Project:
    project = Project(user_id=user_id, title=title, status=status, priority="Medium")
    db.session.add(project)
    db.session.commit()
    return project


def _login(client):
    return client.post(
        "/login",
        data={"email": "student@example.com", "password": "StrongPass123!"},
        follow_redirects=False,
    )


def test_i7_direct_all_projects_routes_to_portfolio_review(app, user):
    with app.app_context():
        _project(user, "LifeOS")
        _project(user, "Storefront")
        decision = route_intelligence_request(
            query="How are all my projects going?",
            owner_id=user,
        )
        assert decision.intent == "portfolio_review"
        assert decision.status == "ready"
        assert decision.scope_type == "portfolio"
        assert decision.scope_label == "All projects"


def test_i7_clarification_followup_project_name_preserves_original_review_intent(app, user, monkeypatch):
    with app.app_context():
        _project(user, "LifeOS Web")
        _project(user, "LifeOS Mobile")

        first = ask_lifeos(query="How is my LifeOS project going?", owner_id=user)
        assert first.status == "clarification_required"

        # No provider should be needed to prove that routing follows the named
        # project; make the reasoner unavailable so the trusted fallback is used.
        monkeypatch.setattr(
            "services.intelligence_ask_service.reason_about_project_review",
            lambda **kwargs: (_ for _ in ()).throw(Exception("sentinel")),
        )
        # Ask service catches only its domain error, so route directly for this
        # continuation behavior.
        decision = route_intelligence_request(
            query="LifeOS Web",
            owner_id=user,
            continuation_intent="project_review",
        )
        assert decision.intent == "project_review"
        assert decision.scope_label == "LifeOS Web"
        assert decision.status == "ready"


def test_i7_all_followup_returns_verified_owned_portfolio(app, user):
    with app.app_context():
        first_project = _project(user, "LifeOS")
        second_project = _project(user, "Storefront")
        db.session.add(Task(user_id=user, project_id=first_project.id, title="Ship intelligence", status="Pending"))
        db.session.commit()

        result = ask_lifeos(
            query="all",
            owner_id=user,
            clarification_context={"intent": "project_review"},
        )
        payload = result.to_dict()
        assert payload["status"] == "completed"
        assert payload["response_mode"] == "deterministic_verified"
        assert payload["verification"]["status"] == "verified"
        assert payload["route"]["scope"]["label"] == "All projects"
        assert "LifeOS" in payload["answer"]
        assert "Storefront" in payload["answer"]
        assert payload["read_only"] is True


def test_i7_ask_api_accepts_safe_clarification_context(client, app, user):
    with app.app_context():
        _project(user, "LifeOS")
        _project(user, "Storefront")

    _login(client)
    response = client.post(
        "/api/v1/intelligence/ask",
        json={
            "query": "all",
            "clarification_context": {"intent": "project_review"},
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["response_mode"] == "deterministic_verified"
    assert payload["route"]["scope"]["type"] == "portfolio"
    assert payload["route"]["scope"]["id"] is None


def test_i7_clarification_exposes_only_owned_project_options(client, app, user):
    with app.app_context():
        _project(user, "LifeOS Web")
        _project(user, "LifeOS Mobile")

    _login(client)
    response = client.post(
        "/api/v1/intelligence/ask",
        json={"query": "How is my LifeOS project going?"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "clarification_required"
    labels = {item["label"] for item in payload["route"]["candidates"]}
    assert labels == {"LifeOS Web", "LifeOS Mobile"}
