"""Regression coverage for the React UI parity bridge."""

from __future__ import annotations

from database import db
from models import Project


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "StrongPass123!"},
    )
    assert response.status_code == 200


def _legacy_get(client, path: str, query_string=None):
    return client.get(
        "/api/v1/legacy-proxy",
        query_string=query_string,
        headers={
            "X-LifeOS-Legacy-Path": path,
            "Accept": "text/html",
        },
    )


def test_parity_meta_is_available(client):
    response = client.get("/api/v1/legacy-proxy/meta")
    assert response.status_code == 200
    assert response.get_json()["mode"] == "react-ui-parity"


def test_public_login_renders_exact_legacy_public_shell(client):
    response = _legacy_get(client, "/login")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'class="public-body"' in html
    assert "LifeOS AI" in html
    assert "Log In" in html
    assert response.headers["X-LifeOS-UI-Parity"] == "legacy-controller"


def test_protected_screen_returns_frontend_redirect_when_logged_out(client):
    response = _legacy_get(client, "/dashboard")
    assert response.status_code == 204
    assert response.headers["X-LifeOS-Legacy-Redirect"].startswith("/login?next=/dashboard")


def test_dashboard_keeps_legacy_shell_and_active_endpoint(client, user):
    _login(client)
    response = _legacy_get(client, "/dashboard")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'class="app-body studio-theme' in html
    assert "Turn today into" in html
    assert "Dashboard" in html
    assert 'navigation-link\n                    active' in html


def test_project_details_are_dispatched_through_existing_controller(client, user, app):
    with app.app_context():
        project = Project(
            user_id=user,
            title="Parity Project",
            goal="Keep the existing workspace behavior",
        )
        db.session.add(project)
        db.session.commit()
        project_id = project.id

    _login(client)
    response = _legacy_get(client, f"/projects/{project_id}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Parity Project" in html
    assert "Project Studio" in html or "project" in html.lower()


def test_proxy_rejects_recursive_api_dispatch(client):
    response = _legacy_get(client, "/api/v1/health")
    assert response.status_code == 404


def test_query_string_reaches_existing_controller(client, user):
    _login(client)
    response = _legacy_get(client, "/notes/", {"q": "needle"})
    assert response.status_code == 200
    assert "Notes" in response.get_data(as_text=True)
