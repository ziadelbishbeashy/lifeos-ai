from __future__ import annotations

from datetime import date, timedelta

import pytest

from database import db
from models import Document, Project, Task, User
from services.intelligence_executor_service import execute_intelligence_plan
from services.intelligence_planner_service import plan_project_review
from services.project_review_intelligence_service import review_owned_project
from services.workspace_context_service import WorkspaceContextNotFoundError


def _project(user_id: int, title: str = "Intelligence Project") -> Project:
    project = Project(
        user_id=user_id,
        title=title,
        status="In Progress",
        priority="High",
        progress=25,
        deadline=date.today() + timedelta(days=5),
    )
    db.session.add(project)
    db.session.commit()
    return project


def _login(client):
    return client.post(
        "/login",
        data={"email": "student@example.com", "password": "StrongPass123!"},
        follow_redirects=False,
    )


def test_project_review_plan_contains_only_reviewed_read_only_tools(app, user):
    with app.app_context():
        project = _project(user)
        plan = plan_project_review(project_id=project.id)

        assert plan.intent == "project_review"
        assert [step.tool_name for step in plan.steps] == [
            "project.get_summary",
            "project.get_tasks",
            "project.get_documents",
            "project.get_recent_notes",
        ]


def test_project_review_executor_preserves_ownership(app, user):
    with app.app_context():
        other = User(name="Other", email="other-intelligence@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.commit()
        project = _project(other.id, "Other Private Project")
        plan = plan_project_review(project_id=project.id)

        with pytest.raises(WorkspaceContextNotFoundError):
            execute_intelligence_plan(plan=plan, owner_id=user)


def test_project_review_separates_facts_from_suggestions(app, user):
    with app.app_context():
        project = _project(user)
        db.session.add_all(
            [
                Task(
                    user_id=user,
                    project_id=project.id,
                    title="Fix deployment blocker",
                    status="Blocked",
                    importance="Critical",
                ),
                Task(
                    user_id=user,
                    project_id=project.id,
                    title="Overdue payment test",
                    status="Pending",
                    importance="High",
                    deadline=date.today() - timedelta(days=2),
                ),
            ]
        )
        db.session.commit()

        review = review_owned_project(project_id=project.id, owner_id=user)
        payload = review.to_dict()

        assert payload["read_only"] is True
        assert payload["attention_level"] == "high"
        assert any(item["kind"] == "verified_fact" for item in payload["signals"])
        assert any(item["kind"] == "calculated_fact" for item in payload["signals"])
        assert all(item["kind"] == "suggestion" for item in payload["suggestions"])
        assert any(fact["fact_type"] == "verified" for fact in payload["facts"])
        assert any(fact["fact_type"] == "calculated" for fact in payload["facts"])


def test_project_review_does_not_treat_stale_analysis_as_current(app, user):
    with app.app_context():
        project = _project(user)
        document = Document(
            user_id=user,
            project_id=project.id,
            filename="requirements.pdf",
            file_path="requirements.pdf",
            extracted_text="Current requirements text",
            is_current_version=True,
        )
        db.session.add(document)
        db.session.commit()

        review = review_owned_project(project_id=project.id, owner_id=user)
        # No analysis exists, so the intelligence layer may suggest analysis but
        # must never invent a current structured finding.
        assert all(
            signal.title != "Current requirements"
            for signal in review.signals
        )
        assert review.to_dict()["read_only"] is True


def test_project_review_api_is_owned_and_product_level(client, app, user):
    with app.app_context():
        project = _project(user, "Visible Intelligence Project")
        project_id = project.id

    _login(client)
    response = client.get(f"/api/v1/intelligence/projects/{project_id}/review")

    assert response.status_code == 200
    payload = response.get_json()["review"]
    assert payload["project"]["title"] == "Visible Intelligence Project"
    assert payload["read_only"] is True
    assert "tool_data" not in payload
    assert "tool_name" not in str(payload)
    assert "chunk_id" not in str(payload)
    assert "embedding" not in str(payload).lower()


def test_project_review_api_hides_other_users_project(client, app, user):
    with app.app_context():
        other = User(name="Other", email="other-review@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.commit()
        project = _project(other.id, "Hidden Review Project")
        project_id = project.id

    _login(client)
    response = client.get(f"/api/v1/intelligence/projects/{project_id}/review")
    assert response.status_code == 404
