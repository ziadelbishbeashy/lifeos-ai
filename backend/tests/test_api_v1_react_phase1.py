"""React migration Phase 1 API contract tests."""

from datetime import date, timedelta

from database import db
from models import Document, Note, Project, Task


def test_csrf_endpoint_returns_token(client):
    response = client.get("/api/v1/csrf")

    assert response.status_code == 200
    assert response.get_json()["csrf_token"]


def test_api_login_session_and_logout(client, user):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "student@example.com",
            "password": "StrongPass123!",
            "remember": True,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["authenticated"] is True
    assert payload["user"]["id"] == user

    session_response = client.get("/api/v1/session")
    assert session_response.status_code == 200
    assert session_response.get_json()["authenticated"] is True

    logout_response = client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 200
    assert logout_response.get_json()["authenticated"] is False

    after_logout = client.get("/api/v1/session")
    assert after_logout.get_json()["authenticated"] is False


def test_api_login_rejects_bad_password(client, user):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "student@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "invalid_credentials"


def test_api_registration_reuses_existing_account_rules(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "React Student",
            "email": "react@example.com",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        },
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["authenticated"] is True
    assert payload["user"]["email"] == "react@example.com"


def test_api_registration_validation_is_not_duplicated_in_frontend(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "R",
            "email": "invalid",
            "password": "short",
            "confirm_password": "different",
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "validation_error"


def test_dashboard_api_requires_authentication(client):
    response = client.get("/api/v1/dashboard")

    assert response.status_code == 401
    assert response.get_json()["error"] == "authentication_required"


def test_dashboard_api_matches_workspace_metrics(app, client, user):
    with app.app_context():
        project = Project(
            user_id=user,
            title="React Migration",
            status="In Progress",
            priority="High",
            progress=40,
        )
        db.session.add(project)
        db.session.flush()

        db.session.add_all(
            [
                Task(
                    user_id=user,
                    project_id=project.id,
                    title="Migrate dashboard",
                    status="In Progress",
                    importance="High",
                    priority_score=90,
                    deadline=date.today() + timedelta(days=2),
                ),
                Task(
                    user_id=user,
                    title="Old completed task",
                    status="Completed",
                    importance="Low",
                ),
                Note(
                    user_id=user,
                    project_id=project.id,
                    title="Migration note",
                    content="Keep backend services canonical.",
                ),
                Document(
                    project_id=project.id,
                    filename="architecture.pdf",
                    file_path="architecture.pdf",
                    extracted_text="Architecture",
                ),
            ]
        )
        db.session.commit()

    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "student@example.com",
            "password": "StrongPass123!",
        },
    )
    assert login.status_code == 200

    response = client.get("/api/v1/dashboard")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["counts"]["projects"] == 1
    assert payload["counts"]["active_projects"] == 1
    assert payload["counts"]["tasks"] == 2
    assert payload["counts"]["open_tasks"] == 1
    assert payload["counts"]["completed_tasks"] == 1
    assert payload["counts"]["notes"] == 1
    assert payload["counts"]["documents"] == 1
    assert payload["completion_rate"] == 50
    assert payload["average_project_progress"] == 40
    assert payload["focus_task"]["title"] == "Migrate dashboard"
    assert payload["focus_task"]["project"]["title"] == "React Migration"
    assert payload["latest_projects"][0]["title"] == "React Migration"


def test_api_responses_are_private_no_store(client):
    response = client.get("/api/v1/session")

    assert "no-store" in response.headers.get("Cache-Control", "")
