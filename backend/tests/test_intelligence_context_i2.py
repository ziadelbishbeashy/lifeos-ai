from __future__ import annotations

from database import db
from models import Document, Note, Project, Task
from services.intelligence_context_service import collect_owned_project_context


def _project(user_id: int, title: str = "LifeOS") -> Project:
    project = Project(
        user_id=user_id,
        title=title,
        status="In Progress",
        priority="Medium",
        progress=5,
        current_phase="planning and development",
    )
    db.session.add(project)
    db.session.commit()
    return project


def test_i2_project_context_distinguishes_manual_and_task_progress(app, user):
    with app.app_context():
        project = _project(user)
        db.session.add_all(
            [
                Task(user_id=user, project_id=project.id, title="Done", status="Completed"),
                Task(user_id=user, project_id=project.id, title="Open", status="Pending"),
            ]
        )
        db.session.commit()

        context = collect_owned_project_context(project_id=project.id, owner_id=user)
        payload = context.to_dict()
        facts = {item["key"]: item for item in payload["facts"]}

        assert payload["schema_version"] == "lifeos-intelligence-context-v2"
        assert payload["scope"] == {
            "type": "project",
            "id": project.id,
            "label": "LifeOS",
        }
        assert facts["project.manual_progress"]["value"] == 5
        assert facts["project.manual_progress"]["fact_type"] == "verified"
        assert facts["project.task_progress"]["fact_type"] == "calculated"
        assert facts["project.total_tasks"]["value"] == 2
        assert facts["project.completed_tasks"]["value"] == 1
        assert "tool_data" not in payload


def test_i2_context_derives_bounded_recent_activity_from_owned_sources(app, user):
    with app.app_context():
        project = _project(user)
        db.session.add(Task(user_id=user, project_id=project.id, title="Task A"))
        db.session.add(Note(user_id=user, project_id=project.id, title="Note A", content="x"))
        db.session.add(
            Document(
                user_id=user,
                project_id=project.id,
                filename="brief.pdf",
                file_path="brief.pdf",
                extracted_text="brief",
                is_current_version=True,
            )
        )
        db.session.commit()

        payload = collect_owned_project_context(
            project_id=project.id,
            owner_id=user,
        ).to_dict()

        activity_types = {item["source_type"] for item in payload["recent_activity"]}
        assert "project" in activity_types
        assert "task" in activity_types
        assert "note" in activity_types
        assert "document" in activity_types
        assert len(payload["recent_activity"]) <= 12
        assert all("occurred_at" in item for item in payload["recent_activity"])


def test_i2_context_reports_document_analysis_freshness_counts(app, user):
    with app.app_context():
        project = _project(user)
        db.session.add(
            Document(
                user_id=user,
                project_id=project.id,
                filename="not-analysed.pdf",
                file_path="not-analysed.pdf",
                extracted_text="current",
                is_current_version=True,
            )
        )
        db.session.commit()

        payload = collect_owned_project_context(project_id=project.id, owner_id=user).to_dict()
        facts = {item["key"]: item["value"] for item in payload["facts"]}
        assert facts["project.unanalysed_documents"] == 1
        assert facts["project.stale_document_analyses"] == 0
