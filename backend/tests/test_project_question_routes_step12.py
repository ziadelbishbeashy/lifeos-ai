"""Step 12 project question route tests."""

from types import SimpleNamespace

from database import db
from models import Project
import routes.project_routes as project_routes


def _login(client):
    return client.post(
        "/login",
        data={"email": "student@example.com", "password": "StrongPass123!"},
        follow_redirects=False,
    )


def test_project_question_route_is_owned_and_redirects_to_ask_tab(client, app, user, monkeypatch):
    with app.app_context():
        project = Project(user_id=user, title="LifeOS")
        db.session.add(project)
        db.session.commit()
        project_id = project.id

    monkeypatch.setattr(
        project_routes,
        "ask_owned_project_documents",
        lambda **kwargs: SimpleNamespace(
            reused_existing=False,
            question=SimpleNamespace(sources=[{"document_id": 1}]),
        ),
    )

    _login(client)
    response = client.post(
        f"/projects/{project_id}/questions",
        data={"question": "What are the risks?"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/projects/{project_id}#ask-project"
    )
