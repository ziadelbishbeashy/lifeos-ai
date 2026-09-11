"""Tests for Document Brain task suggestions."""

import json

from database import db
from models import (
    Document,
    DocumentAIAnalysis,
    Project,
    Task,
)
from services.document_task_suggestion_service import (
    MATCH_THRESHOLD,
    build_document_task_suggestions,
    calculate_task_match_score,
)


def create_analysis_data(
    *,
    user_id: int,
):
    project = Project(
        user_id=user_id,
        title="LifeOS",
        status="In Progress",
        priority="High",
    )

    db.session.add(project)
    db.session.commit()

    existing_task = Task(
        user_id=user_id,
        project_id=project.id,
        title="Implement secure PDF upload",
        description="Validate and store PDF files.",
        module="Document Brain",
        importance="High",
        difficulty="Medium",
        deadline=None,
        status="Pending",
        priority_score=80,
        reason="Existing project task.",
    )

    document = Document(
        project_id=project.id,
        filename="requirements.pdf",
        file_path="stored/requirements.pdf",
        extracted_text="Readable PDF text.",
    )

    db.session.add_all(
        [
            existing_task,
            document,
        ]
    )
    db.session.commit()

    analysis = DocumentAIAnalysis(
        document_id=document.id,
        user_id=user_id,
        provider="gemini",
        model="test-model",
        status="Completed",
        document_type="Requirements Document",
        summary="Document summary.",
        insights_json=json.dumps(
            {
                "action_items": [
                    {
                        "title": "Build secure PDF upload",
                        "description": (
                            "Add safe PDF upload support."
                        ),
                        "priority": "High",
                        "deadline": "2026-08-15",
                        "source": {
                            "page": 3,
                            "section": "Document Brain",
                            "evidence": (
                                "The system must upload PDFs."
                            ),
                        },
                    },
                    {
                        "title": "Create document question answering",
                        "description": (
                            "Allow grounded questions."
                        ),
                        "priority": "Medium",
                        "deadline": None,
                        "source": {
                            "page": 5,
                        },
                    },
                ]
            }
        ),
    )

    db.session.add(analysis)
    db.session.commit()

    return (
        document,
        analysis,
        existing_task,
    )


def test_similarity_detects_related_tasks():
    score = calculate_task_match_score(
        "Build secure PDF upload",
        "Implement secure PDF upload",
    )

    assert score >= MATCH_THRESHOLD


def test_suggestions_are_built_with_duplicate_warning(
    app,
    user,
):
    with app.app_context():
        (
            document,
            analysis,
            existing_task,
        ) = create_analysis_data(
            user_id=user
        )

        suggestions = build_document_task_suggestions(
            analysis=analysis,
            document=document,
            user_id=user,
        )

        assert len(suggestions) == 2

        first = suggestions[0]

        assert first.status == "Pending"
        assert first.priority == "High"
        assert first.deadline.isoformat() == (
            "2026-08-15"
        )

        assert first.matched_task_id == (
            existing_task.id
        )

        assert first.match_score >= MATCH_THRESHOLD
        assert first.source["page"] == 3

        second = suggestions[1]

        assert second.matched_task_id is None
        assert second.status == "Pending"


def test_duplicate_action_titles_are_removed(
    app,
    user,
):
    with app.app_context():
        document = Document(
            filename="test.pdf",
            file_path="test.pdf",
        )

        analysis = DocumentAIAnalysis(
            document_id=1,
            user_id=user,
            provider="gemini",
            model="test",
            status="Completed",
            insights_json=json.dumps(
                {
                    "action_items": [
                        {
                            "title": "Create dashboard",
                        },
                        {
                            "title": "Create dashboard",
                        },
                    ]
                }
            ),
        )

        # The builder only needs matching IDs for
        # this duplicate-normalisation test.
        document.id = 1

        suggestions = build_document_task_suggestions(
            analysis=analysis,
            document=document,
            user_id=user,
        )

        assert len(suggestions) == 1