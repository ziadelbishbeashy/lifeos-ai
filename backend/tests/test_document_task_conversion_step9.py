"""Step 9 integration tests for confirmed document-to-task conversion."""

from datetime import date

from database import db
from models import (
    Document,
    DocumentAIAnalysis,
    DocumentTaskSuggestion,
    Project,
    Task,
)
from services.document_task_action_service import (
    DocumentSuggestionDuplicateError,
    DocumentSuggestionTaskInput,
    approve_document_suggestion,
    bulk_create_document_suggestions,
    list_project_document_suggestions,
)
from services.project_service import build_project_workspace
from services.task_service import delete_task


def create_document_suggestion(
    *,
    user_id: int,
    title: str = "Prepare deployment checklist",
    matched_task_id: int | None = None,
):
    project = Project(
        user_id=user_id,
        title="LifeOS",
        status="In Progress",
        priority="High",
    )

    document = Document(
        project=project,
        filename="requirements.pdf",
        file_path="stored/requirements.pdf",
        extracted_text="Readable content.",
    )

    db.session.add_all([project, document])
    db.session.flush()

    analysis = DocumentAIAnalysis(
        document_id=document.id,
        user_id=user_id,
        provider="gemini",
        model="test-model",
        status="Completed",
        summary="Summary",
        insights_json="{}",
    )

    db.session.add(analysis)
    db.session.flush()

    suggestion = DocumentTaskSuggestion(
        analysis_id=analysis.id,
        document_id=document.id,
        user_id=user_id,
        title=title,
        description="Prepare the production deployment checklist.",
        tags="deployment, release",
        priority="High",
        deadline=date(2026, 8, 30),
        source_json=(
            '{"page": 14, "section": "Release", '
            '"evidence": "Prepare the deployment checklist."}'
        ),
        status="Pending",
        matched_task_id=matched_task_id,
        match_score=0.0,
    )

    db.session.add(suggestion)
    db.session.commit()

    return project, document, analysis, suggestion


def test_edit_first_can_change_all_approved_task_fields(app, user):
    with app.app_context():
        source_project, _, _, suggestion = create_document_suggestion(
            user_id=user
        )

        other_project = Project(
            user_id=user,
            title="Release Project",
            status="In Progress",
            priority="Medium",
        )
        db.session.add(other_project)
        db.session.commit()

        task_input = DocumentSuggestionTaskInput(
            project_id=other_project.id,
            title="Finalize deployment checklist",
            description="Review owners and release gates.",
            priority="Critical",
            deadline=date(2026, 9, 1),
            tags="release, qa",
            status="In Progress",
        )

        task = approve_document_suggestion(
            suggestion=suggestion,
            user_id=user,
            task_input=task_input,
        )

        assert task.project_id == other_project.id
        assert task.title == "Finalize deployment checklist"
        assert task.description == "Review owners and release gates."
        assert task.importance == "Critical"
        assert task.deadline == date(2026, 9, 1)
        assert task.tags == "release, qa"
        assert task.status == "In Progress"

        assert suggestion.status == "Approved"
        assert suggestion.lifecycle_label == "Created"
        assert suggestion.document.project_id == source_project.id
        assert suggestion.source["page"] == 14


def test_duplicate_requires_explicit_create_anyway(app, user):
    with app.app_context():
        project, _, _, suggestion = create_document_suggestion(
            user_id=user,
            title="Prepare deployment checklist",
        )

        existing = Task(
            user_id=user,
            project_id=project.id,
            title="Prepare deployment checklist",
            importance="High",
            difficulty="Medium",
            status="Pending",
        )
        db.session.add(existing)
        db.session.commit()

        try:
            approve_document_suggestion(
                suggestion=suggestion,
                user_id=user,
            )
            assert False, "duplicate should require explicit override"
        except DocumentSuggestionDuplicateError as error:
            assert error.task.id == existing.id

        created = approve_document_suggestion(
            suggestion=suggestion,
            user_id=user,
            allow_possible_duplicate=True,
        )

        assert created.id != existing.id
        assert suggestion.status == "Approved"


def test_bulk_create_skips_possible_duplicates(app, user):
    with app.app_context():
        project, document, analysis, first = create_document_suggestion(
            user_id=user,
            title="Prepare deployment checklist",
        )

        existing = Task(
            user_id=user,
            project_id=project.id,
            title="Prepare deployment checklist",
            importance="Medium",
            difficulty="Medium",
            status="Pending",
        )

        second = DocumentTaskSuggestion(
            analysis_id=analysis.id,
            document_id=document.id,
            user_id=user,
            title="Write release notes",
            description="Prepare final release notes.",
            priority="Medium",
            status="Pending",
            match_score=0.0,
        )

        db.session.add_all([existing, second])
        db.session.commit()

        result = bulk_create_document_suggestions(
            suggestion_ids=[first.id, second.id],
            user_id=user,
            document_id=document.id,
        )

        assert result.created_count == 1
        assert result.duplicate_count == 1
        assert result.created_tasks[0].title == "Write release notes"
        assert first.status == "Pending"
        assert second.status == "Approved"


def test_project_workspace_contains_document_suggestion_history(app, user):
    with app.app_context():
        project, _, _, suggestion = create_document_suggestion(
            user_id=user
        )

        workspace = build_project_workspace(
            project.id,
            user,
        )

        assert suggestion.id in {
            item.id
            for item in workspace["document_suggestions"]
        }
        assert workspace["pending_document_suggestion_count"] == 1

        listed = list_project_document_suggestions(
            project_id=project.id,
            user_id=user,
        )
        assert listed[0].id == suggestion.id


def test_deleting_created_task_returns_document_suggestion_to_review(app, user):
    with app.app_context():
        _, _, _, suggestion = create_document_suggestion(
            user_id=user
        )

        task = approve_document_suggestion(
            suggestion=suggestion,
            user_id=user,
        )

        task_id = task.id
        suggestion_id = suggestion.id

        delete_task(task)

        refreshed = db.session.get(
            DocumentTaskSuggestion,
            suggestion_id,
        )

        assert db.session.get(Task, task_id) is None
        assert refreshed.status == "Pending"
        assert refreshed.created_task_id is None
