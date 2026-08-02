"""Tests for Document Brain suggestion approval actions."""

from database import db
from models import (
    Document,
    DocumentTaskSuggestion,
    Project,
    Task,
)
from services.document_task_action_service import (
    DocumentSuggestionWorkflowError,
    approve_document_suggestion,
    link_suggestion_to_existing_task,
    reject_document_suggestion,
)


def create_project_document(
    *,
    user_id: int,
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
        extracted_text="Readable text.",
    )

    db.session.add_all(
        [
            project,
            document,
        ]
    )
    db.session.commit()

    return project, document


def create_suggestion(
    *,
    user_id: int,
    document: Document,
    matched_task_id=None,
):
    suggestion = DocumentTaskSuggestion(
        analysis_id=1,
        document_id=document.id,
        user_id=user_id,
        title="Implement document search",
        description="Add grounded document search.",
        priority="High",
        deadline=None,
        source_json=(
            '{"page": 4, '
            '"section": "Document Brain", '
            '"evidence": "Add document search."}'
        ),
        status="Pending",
        matched_task_id=matched_task_id,
        match_score=0.0,
    )

    db.session.add(suggestion)
    db.session.commit()

    return suggestion


def test_approved_suggestion_creates_task(
    app,
    user,
):
    with app.app_context():
        project, document = create_project_document(
            user_id=user
        )

        suggestion = create_suggestion(
            user_id=user,
            document=document,
        )

        task = approve_document_suggestion(
            suggestion=suggestion,
            user_id=user,
        )

        assert task.project_id == project.id
        assert task.module == "Document Brain"
        assert task.importance == "High"
        assert task.status == "Pending"
        assert task.priority_score == 80

        assert suggestion.status == "Approved"
        assert suggestion.created_task_id == task.id


def test_possible_duplicate_requires_confirmation(
    app,
    user,
):
    with app.app_context():
        project, document = create_project_document(
            user_id=user
        )

        existing_task = Task(
            user_id=user,
            project_id=project.id,
            title="Implement document search",
            module="Document Brain",
            importance="High",
            difficulty="Medium",
            status="Pending",
            priority_score=80,
        )

        db.session.add(existing_task)
        db.session.commit()

        suggestion = create_suggestion(
            user_id=user,
            document=document,
            matched_task_id=existing_task.id,
        )

        try:
            approve_document_suggestion(
                suggestion=suggestion,
                user_id=user,
            )

            assert False

        except DocumentSuggestionWorkflowError:
            pass


def test_duplicate_can_be_created_after_confirmation(
    app,
    user,
):
    with app.app_context():
        project, document = create_project_document(
            user_id=user
        )

        existing_task = Task(
            user_id=user,
            project_id=project.id,
            title="Implement document search",
            module="Document Brain",
            importance="High",
            difficulty="Medium",
            status="Pending",
            priority_score=80,
        )

        db.session.add(existing_task)
        db.session.commit()

        suggestion = create_suggestion(
            user_id=user,
            document=document,
            matched_task_id=existing_task.id,
        )

        created_task = approve_document_suggestion(
            suggestion=suggestion,
            user_id=user,
            allow_possible_duplicate=True,
        )

        assert created_task.id != existing_task.id
        assert suggestion.status == "Approved"


def test_suggestion_can_link_to_existing_task(
    app,
    user,
):
    with app.app_context():
        project, document = create_project_document(
            user_id=user
        )

        existing_task = Task(
            user_id=user,
            project_id=project.id,
            title="Implement document search",
            module="Document Brain",
            importance="High",
            difficulty="Medium",
            status="Pending",
            priority_score=80,
        )

        db.session.add(existing_task)
        db.session.commit()

        suggestion = create_suggestion(
            user_id=user,
            document=document,
            matched_task_id=existing_task.id,
        )

        result = link_suggestion_to_existing_task(
            suggestion=suggestion,
            user_id=user,
        )

        assert result.id == existing_task.id
        assert suggestion.status == "Linked"
        assert suggestion.created_task_id == existing_task.id


def test_suggestion_can_be_rejected(
    app,
    user,
):
    with app.app_context():
        _, document = create_project_document(
            user_id=user
        )

        suggestion = create_suggestion(
            user_id=user,
            document=document,
        )

        result = reject_document_suggestion(
            suggestion
        )

        assert result == "rejected"
        assert suggestion.status == "Rejected"