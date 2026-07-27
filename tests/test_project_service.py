"""Unit tests for the project service layer."""

from datetime import date

from database import db
from models import Project
from services.project_service import (
    ProjectValidationError,
    build_project_input,
    create_project,
    delete_project,
    get_owned_project,
    update_project,
)


def _project_input(**overrides):
    values = {
        "title": "Database Project",
        "project_type": "University Course",
        "description": "Create the semester database project.",
        "goal": "Submit a complete database system.",
        "status": "In Progress",
        "priority": "High",
        "start_date": "2026-07-01",
        "deadline": "2026-08-01",
        "progress": "25",
    }
    values.update(overrides)
    return build_project_input(values)


def test_build_project_input_normalises_values():
    data = _project_input(title="  Database Project  ", progress="140")

    assert data.title == "Database Project"
    assert data.progress == 100
    assert data.start_date == date(2026, 7, 1)
    assert data.deadline == date(2026, 8, 1)


def test_create_project_assigns_owner(app, user):
    with app.app_context():
        project = create_project(user, _project_input())

        assert project.user_id == user
        assert project.title == "Database Project"
        assert get_owned_project(project.id, user).id == project.id


def test_project_validation_rejects_deadline_before_start(app, user):
    with app.app_context():
        try:
            create_project(
                user,
                _project_input(deadline="2026-06-30"),
            )
        except ProjectValidationError as error:
            assert "cannot be before" in str(error)
        else:
            raise AssertionError("ProjectValidationError was not raised")

        assert Project.query.count() == 0


def test_update_and_delete_project(app, user):
    with app.app_context():
        project = create_project(user, _project_input())
        project_id = project.id

        updated = update_project(
            project,
            _project_input(title="Updated Project", progress="60"),
        )
        assert updated.title == "Updated Project"
        assert updated.progress == 60

        deleted_title = delete_project(updated)
        assert deleted_title == "Updated Project"
        assert db.session.get(Project, project_id) is None
