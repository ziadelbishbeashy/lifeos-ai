"""Step 13A DocumentComparison model tests."""

import json

import pytest
from sqlalchemy.exc import IntegrityError

from database import db
from models import (
    Document,
    DocumentComparison,
    Project,
)


def _documents(user):
    project = Project(
        user_id=user,
        title="Comparison project",
    )
    document_a = Document(
        project=project,
        filename="architecture-v1.pdf",
        file_path="architecture-v1.pdf",
        extracted_text="Authentication is required.",
    )
    document_b = Document(
        project=project,
        filename="architecture-v2.pdf",
        file_path="architecture-v2.pdf",
        extracted_text="Project membership is also required.",
    )
    db.session.add_all(
        [
            project,
            document_a,
            document_b,
        ]
    )
    db.session.commit()

    return (
        document_a,
        document_b,
    )


def test_document_comparison_findings_round_trip(app, user):
    with app.app_context():
        document_a, document_b = _documents(user)

        comparison = DocumentComparison(
            user_id=user,
            document_a_id=document_a.id,
            document_b_id=document_b.id,
            summary="One access-control rule changed.",
            findings_json=json.dumps(
                [
                    {
                        "category": "changed",
                        "topic": "Access control",
                    }
                ]
            ),
            provider="test",
            model="test-model",
            status="Completed",
            source_fingerprint="a" * 64,
        )
        db.session.add(comparison)
        db.session.commit()

        assert comparison.document_a.id == document_a.id
        assert comparison.document_b.id == document_b.id
        assert comparison.findings == [
            {
                "category": "changed",
                "topic": "Access control",
            }
        ]


def test_document_comparison_invalid_findings_are_safe(app, user):
    with app.app_context():
        document_a, document_b = _documents(user)

        comparison = DocumentComparison(
            user_id=user,
            document_a_id=document_a.id,
            document_b_id=document_b.id,
            findings_json="{broken-json",
            provider="test",
            model="test-model",
            status="Completed",
        )

        assert comparison.findings == []


def test_database_rejects_comparing_document_with_itself(app, user):
    with app.app_context():
        document_a, _ = _documents(user)

        comparison = DocumentComparison(
            user_id=user,
            document_a_id=document_a.id,
            document_b_id=document_a.id,
            provider="test",
            model="test-model",
            status="Completed",
        )
        db.session.add(comparison)

        with pytest.raises(
            IntegrityError
        ):
            db.session.commit()

        db.session.rollback()
