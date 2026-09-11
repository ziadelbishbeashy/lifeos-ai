"""React migration Phase 2 API contract and ownership tests."""

from database import db
from models import Document, Project, Task, User


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "StrongPass123!"},
    )
    assert response.status_code == 200


def test_phase2_endpoints_require_authentication(client):
    assert client.get("/api/v1/projects").status_code == 401
    assert client.get("/api/v1/tasks").status_code == 401


def test_project_api_crud_reuses_project_service(client, user):
    _login(client)

    created = client.post(
        "/api/v1/projects",
        json={
            "title": "React Phase 2",
            "goal": "Move project management to React safely.",
            "description": "Preserve the proven project workspace while changing transport.",
            "project_type": "Full-Stack AI System",
            "tech_stack": "React, Flask",
            "current_phase": "Native parity",
            "status": "In Progress",
            "priority": "High",
            "progress": 25,
            "deadline": "2026-09-30",
        },
    )
    assert created.status_code == 201
    project = created.get_json()["item"]
    assert project["title"] == "React Phase 2"
    assert project["priority"] == "High"

    listed = client.get("/api/v1/projects")
    assert listed.status_code == 200
    payload = listed.get_json()
    assert payload["counts"]["total"] == 1
    assert payload["items"][0]["id"] == project["id"]
    # Native Projects parity needs the same product-level card fields the
    # legacy template displayed, without exposing provider/RAG internals.
    assert payload["items"][0]["project_type"] == "Full-Stack AI System"
    assert payload["items"][0]["goal"] == "Move project management to React safely."
    assert payload["items"][0]["tech_stack"] == "React, Flask"
    assert payload["items"][0]["current_phase"] == "Native parity"
    assert payload["items"][0]["note_count"] == 0

    updated = client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"current_phase": "Frontend parity", "progress": 40},
    )
    assert updated.status_code == 200
    assert updated.get_json()["item"]["current_phase"] == "Frontend parity"
    # PATCH merges with the current model instead of blanking omitted fields.
    assert updated.get_json()["item"]["title"] == "React Phase 2"

    details = client.get(f"/api/v1/projects/{project['id']}")
    assert details.status_code == 200
    assert details.get_json()["project"]["progress"] == 40

    deleted = client.delete(f"/api/v1/projects/{project['id']}")
    assert deleted.status_code == 200
    assert deleted.get_json()["deleted"] is True


def test_project_api_keeps_backend_validation_authoritative(client, user):
    _login(client)
    response = client.post(
        "/api/v1/projects",
        json={"title": "", "status": "Not a status"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "validation_error"


def test_task_api_crud_toggle_and_project_scope(client, user):
    _login(client)
    project_response = client.post(
        "/api/v1/projects",
        json={"title": "Task API Project", "status": "In Progress"},
    )
    project_id = project_response.get_json()["item"]["id"]

    created = client.post(
        "/api/v1/tasks",
        json={
            "title": "Wire React Query",
            "project_id": project_id,
            "importance": "High",
            "difficulty": "Medium",
            "status": "In Progress",
            "deadline": "2026-09-01",
        },
    )
    assert created.status_code == 201
    task = created.get_json()["item"]
    assert task["project_id"] == project_id
    assert task["project"]["title"] == "Task API Project"

    listed = client.get("/api/v1/tasks").get_json()
    assert listed["counts"]["total"] == 1
    assert listed["counts"]["project"] == 1

    toggled = client.post(f"/api/v1/tasks/{task['id']}/toggle")
    assert toggled.status_code == 200
    assert toggled.get_json()["item"]["status"] == "Completed"

    updated = client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"title": "Wire React Query everywhere", "status": "In Progress"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["item"]["title"] == "Wire React Query everywhere"
    assert updated.get_json()["item"]["project_id"] == project_id

    workspace = client.get(f"/api/v1/projects/{project_id}").get_json()
    assert workspace["metrics"]["total_tasks"] == 1
    assert workspace["tasks"][0]["title"] == "Wire React Query everywhere"

    deleted = client.delete(f"/api/v1/tasks/{task['id']}")
    assert deleted.status_code == 200
    assert deleted.get_json()["project_id"] == project_id


def test_phase2_api_fails_closed_on_cross_user_resources(app, client, user):
    with app.app_context():
        outsider = User(name="Other User", email="other@example.com")
        outsider.set_password("StrongPass123!")
        db.session.add(outsider)
        db.session.flush()
        private_project = Project(user_id=outsider.id, title="Private Project")
        db.session.add(private_project)
        db.session.flush()
        private_task = Task(user_id=outsider.id, project_id=private_project.id, title="Private Task")
        db.session.add(private_task)
        db.session.commit()
        project_id = private_project.id
        task_id = private_task.id

    _login(client)
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 404
    assert client.patch(f"/api/v1/projects/{project_id}", json={"title": "Nope"}).status_code == 404
    assert client.delete(f"/api/v1/projects/{project_id}").status_code == 404
    assert client.get(f"/api/v1/tasks/{task_id}").status_code == 404
    assert client.patch(f"/api/v1/tasks/{task_id}", json={"title": "Nope"}).status_code == 404
    assert client.delete(f"/api/v1/tasks/{task_id}").status_code == 404


def test_project_workspace_does_not_mix_historical_documents_by_default(app, client, user):
    with app.app_context():
        project = Project(user_id=user, title="Versioned Evidence")
        db.session.add(project)
        db.session.flush()
        db.session.add_all(
            [
                Document(
                    project_id=project.id,
                    filename="current.pdf",
                    file_path="current.pdf",
                    extracted_text="current evidence",
                    is_current_version=True,
                ),
                Document(
                    project_id=project.id,
                    filename="old.pdf",
                    file_path="old.pdf",
                    extracted_text="historical evidence",
                    is_current_version=False,
                ),
            ]
        )
        db.session.commit()
        project_id = project.id

    _login(client)
    response = client.get(f"/api/v1/projects/{project_id}")
    assert response.status_code == 200
    filenames = [item["filename"] for item in response.get_json()["documents"]]
    assert filenames == ["current.pdf"]


def test_meta_reports_current_react_ui_parity_migration(client):
    response = client.get("/api/v1/meta")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["frontend_migration"] == "react-ui-parity-complete"
    assert "projects" in payload["native_frontend_slices"]
