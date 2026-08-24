"""Unit tests for the task service layer."""

from datetime import date

from database import db
from models import Project, Task
from services.task_service import (
    TaskValidationError,
    build_task_input,
    build_tasks_overview,
    create_task,
    delete_task,
    get_owned_task,
    toggle_task_completion,
    update_task,
)


def _project(app, user, title="Database Project"):
    with app.app_context():
        project = Project(
            user_id=user,
            title=title,
            status="In Progress",
            priority="Medium",
        )
        db.session.add(project)
        db.session.commit()
        return project.id


def _task_input(owner_id, **overrides):
    values = {
        "task_scope": "general",
        "title": "Prepare database report",
        "importance": "High",
        "difficulty": "Medium",
        "status": "Pending",
        "deadline": "2026-08-10",
    }
    values.update(overrides)
    return build_task_input(values, owner_id)


def test_build_task_input_normalises_values(app, user):
    with app.app_context():
        data = _task_input(
            user,
            title="  Prepare database report  ",
            module="  Documentation  ",
        )

        assert data.title == "Prepare database report"
        assert data.module == "Documentation"
        assert data.deadline == date(2026, 8, 10)
        assert data.project_id is None


def test_create_task_assigns_owner(app, user):
    with app.app_context():
        task = create_task(user, _task_input(user))

        assert task.user_id == user
        assert task.title == "Prepare database report"
        assert get_owned_task(task.id, user).id == task.id


def test_project_task_requires_owned_project(app, user):
    project_id = _project(app, user)

    with app.app_context():
        data = _task_input(
            user,
            task_scope="project",
            project_id=str(project_id),
        )
        task = create_task(user, data)

        assert task.project_id == project_id


def test_task_validation_rejects_empty_title(app, user):
    with app.app_context():
        try:
            create_task(user, _task_input(user, title="   "))
        except TaskValidationError as error:
            assert "title is required" in str(error)
        else:
            raise AssertionError("TaskValidationError was not raised")

        assert Task.query.count() == 0


def test_update_toggle_and_delete_task(app, user):
    with app.app_context():
        task = create_task(user, _task_input(user))
        task_id = task.id

        updated = update_task(
            task,
            _task_input(user, title="Updated task", status="In Progress"),
        )
        assert updated.title == "Updated task"
        assert updated.status == "In Progress"

        toggled = toggle_task_completion(updated)
        assert toggled.task.status == "Completed"
        assert toggled.task.completed_at is not None

        deleted = delete_task(toggled.task)
        assert deleted.title == "Updated task"
        assert db.session.get(Task, task_id) is None


def test_tasks_overview_is_scoped_to_owner(app, user):
    with app.app_context():
        create_task(user, _task_input(user, title="My task"))
        overview = build_tasks_overview(user)

        assert overview["total_tasks"] == 1
        assert overview["pending_tasks"] == 1
        assert overview["tasks"][0].title == "My task"
