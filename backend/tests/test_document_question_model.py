"""Tests for saved Document Brain questions."""

import json

from database import db
from models import (
    Document,
    DocumentQuestion,
    Project,
)


def test_document_question_saves_sources(
    app,
    user,
):
    with app.app_context():
        project = Project(
            user_id=user,
            title="Document Q&A",
            status="In Progress",
            priority="High",
        )

        document = Document(
            project=project,
            filename="requirements.pdf",
            file_path="stored/requirements.pdf",
            extracted_text=(
                "--- Page 1 ---\n"
                "The system must support document questions."
            ),
        )

        db.session.add_all(
            [
                project,
                document,
            ]
        )
        db.session.commit()

        question = DocumentQuestion(
            document_id=document.id,
            user_id=user,
            question=(
                "What does the system need to support?"
            ),
            answer=(
                "The system must support document questions."
            ),
            sources_json=json.dumps(
                [
                    {
                        "page": 1,
                        "section": "Requirements",
                        "evidence": (
                            "The system must support "
                            "document questions."
                        ),
                    }
                ]
            ),
            provider="gemini",
            model="test-model",
            status="Completed",
            source_fingerprint="abc123",
        )

        db.session.add(question)
        db.session.commit()

        saved = db.session.get(
            DocumentQuestion,
            question.id,
        )

        assert saved is not None
        assert saved.document_id == document.id
        assert saved.question.startswith("What does")
        assert saved.sources[0]["page"] == 1
        assert saved.sources[0]["section"] == "Requirements"


def test_invalid_sources_return_empty_list(
    app,
    user,
):
    with app.app_context():
        project = Project(
            user_id=user,
            title="Invalid Sources",
            status="In Progress",
            priority="Medium",
        )

        document = Document(
            project=project,
            filename="test.pdf",
            file_path="stored/test.pdf",
        )

        db.session.add_all(
            [
                project,
                document,
            ]
        )
        db.session.commit()

        question = DocumentQuestion(
            document_id=document.id,
            user_id=user,
            question="Test question?",
            answer="Test answer.",
            sources_json="invalid JSON",
            provider="gemini",
            model="test-model",
            status="Completed",
        )

        db.session.add(question)
        db.session.commit()

        assert question.sources == []