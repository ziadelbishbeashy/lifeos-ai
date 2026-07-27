"""Task route, ownership, and isolation tests."""

from database import db
from models import Project, Task, User


def _log_in(client, email="student@example.com", password="StrongPass123!"):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def _create_task(app, owner_id, title="Owned task", project_id=None):
    with app.app_context():
        task = Task(
            user_id=owner_id,
            project_id=project_id,
            title=title,
            status="Pending",
            importance="Medium",
            difficulty="Medium",
        )
        db.session.add(task)
        db.session.commit()
        return task.id


def _create_other_user_task(app):
    with app.app_context():
        other_user = User(name="Other Student", email="other@example.com")
        other_user.set_password("StrongPass123!")
        db.session.add(other_user)
        db.session.flush()

        task = Task(
            user_id=other_user.id,
            title="Private other task",
            status="Pending",
            importance="Medium",
            difficulty="Medium",
        )
        db.session.add(task)
        db.session.commit()
        return task.id


def test_tasks_require_login(client):
    response = client.get("/tasks")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_user_can_create_general_task(client, app, user):
    _log_in(client)

    response = client.post(
        "/tasks/add",
        data={
            "task_scope": "general",
            "title": "Review chapter four",
            "importance": "High",
            "difficulty": "Medium",
            "status": "Pending",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/tasks")

    with app.app_context():
        task = Task.query.filter_by(title="Review chapter four").one()
        assert task.user_id == user
        assert task.project_id is None


def test_user_can_create_project_task(client, app, user):
    with app.app_context():
        project = Project(
            user_id=user,
            title="Networks Project",
            status="In Progress",
            priority="Medium",
        )
        db.session.add(project)
        db.session.commit()
        project_id = project.id

    _log_in(client)
    response = client.post(
        "/tasks/add",
        data={
            "task_scope": "project",
            "project_id": str(project_id),
            "title": "Prepare network diagram",
            "importance": "High",
            "difficulty": "Hard",
            "status": "Pending",
        },
    )

    assert response.status_code == 302
    with app.app_context():
        task = Task.query.filter_by(title="Prepare network diagram").one()
        assert task.project_id == project_id


def test_task_routes_hide_another_users_task(client, app, user):
    other_task_id = _create_other_user_task(app)
    _log_in(client)

    edit_response = client.get(f"/tasks/{other_task_id}/edit")
    toggle_response = client.post(f"/tasks/{other_task_id}/toggle")
    delete_response = client.post(f"/tasks/{other_task_id}/delete")

    assert edit_response.status_code == 404
    assert toggle_response.status_code == 404
    assert delete_response.status_code == 404

    with app.app_context():
        assert db.session.get(Task, other_task_id) is not None


def test_empty_task_title_is_rejected(client, app, user):
    _log_in(client)

    response = client.post(
        "/tasks/add",
        data={
            "task_scope": "general",
            "title": "   ",
            "importance": "Medium",
            "difficulty": "Medium",
            "status": "Pending",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Task title is required" in response.data

    with app.app_context():
        assert Task.query.filter_by(user_id=user).count() == 0


def test_user_can_toggle_and_delete_task(client, app, user):
    task_id = _create_task(app, user)
    _log_in(client)

    toggle_response = client.post(
        f"/tasks/{task_id}/toggle",
        data={"next": "tasks"},
        follow_redirects=False,
    )
    assert toggle_response.status_code == 302

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task.status == "Completed"
        assert task.completed_at is not None

    delete_response = client.post(
        f"/tasks/{task_id}/delete",
        data={"next": "tasks"},
        follow_redirects=False,
    )
    assert delete_response.status_code == 302

    with app.app_context():
        assert db.session.get(Task, task_id) is None
