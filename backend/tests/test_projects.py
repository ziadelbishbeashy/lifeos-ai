"""Project route, ownership, and isolation tests."""

from database import db
from models import Project, User


def _log_in(client, email="student@example.com", password="StrongPass123!"):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def _create_second_user_project(app):
    with app.app_context():
        other_user = User(name="Other Student", email="other@example.com")
        other_user.set_password("StrongPass123!")
        db.session.add(other_user)
        db.session.flush()

        project = Project(
            user_id=other_user.id,
            title="Private Other Project",
            status="In Progress",
            priority="Medium",
        )
        db.session.add(project)
        db.session.commit()
        return project.id


def test_projects_require_login(client):
    response = client.get("/projects")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_user_can_create_owned_project(client, app, user):
    _log_in(client)

    response = client.post(
        "/projects",
        data={
            "title": "Operating Systems Project",
            "status": "In Progress",
            "priority": "High",
            "progress": "10",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/projects")

    with app.app_context():
        project = Project.query.filter_by(
            title="Operating Systems Project"
        ).one()
        assert project.user_id == user


def test_projects_page_lists_only_current_users_projects(client, app, user):
    with app.app_context():
        db.session.add(
            Project(
                user_id=user,
                title="My Visible Project",
                status="In Progress",
                priority="Medium",
            )
        )
        db.session.commit()

    _create_second_user_project(app)
    _log_in(client)

    response = client.get("/projects")

    assert response.status_code == 200
    assert b"My Visible Project" in response.data
    assert b"Private Other Project" not in response.data


def test_project_routes_hide_another_users_project(client, app, user):
    other_project_id = _create_second_user_project(app)
    _log_in(client)

    detail_response = client.get(f"/projects/{other_project_id}")
    edit_response = client.get(f"/projects/{other_project_id}/edit")
    update_response = client.post(
        f"/projects/{other_project_id}/edit",
        data={
            "title": "Stolen Project",
            "status": "In Progress",
            "priority": "Medium",
        },
    )
    delete_response = client.post(
        f"/projects/{other_project_id}/delete"
    )

    assert detail_response.status_code == 404
    assert edit_response.status_code == 404
    assert update_response.status_code == 404
    assert delete_response.status_code == 404

    with app.app_context():
        project = db.session.get(Project, other_project_id)
        assert project is not None
        assert project.title == "Private Other Project"


def test_empty_project_title_is_rejected(client, app, user):
    _log_in(client)

    response = client.post(
        "/projects",
        data={
            "title": "   ",
            "status": "In Progress",
            "priority": "Medium",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Project title is required" in response.data

    with app.app_context():
        assert Project.query.filter_by(user_id=user).count() == 0
