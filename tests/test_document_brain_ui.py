"""Rendering checks for the Phase 2 Document Brain interface."""

from __future__ import annotations

import json

from database import db
from models import (
    Document,
    DocumentAIAnalysis,
    DocumentQuestion,
    Project,
)


def login(client):
    return client.post(
        "/login",
        data={
            "email": "student@example.com",
            "password": "StrongPass123!",
        },
        follow_redirects=True,
    )


def create_document_workspace(
    *,
    user_id: int,
) -> Document:
    project = Project(
        user_id=user_id,
        title="LifeOS UI",
        status="In Progress",
        priority="High",
    )

    document = Document(
        project=project,
        filename="Product Requirements.pdf",
        file_path="stored/product-requirements.pdf",
        extracted_text=(
            "The workspace must protect private project data. "
            "The document also defines deadlines and actions."
        ),
        summary=(
            "A product requirements document covering privacy, "
            "delivery and project actions."
        ),
    )

    db.session.add_all(
        [
            project,
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
        summary=document.summary,
        insights_json=json.dumps(
            {
                "purpose": (
                    "Define the first LifeOS release."
                ),
                "key_points": [
                    {
                        "title": "Private by default",
                        "detail": (
                            "Project data remains private."
                        ),
                        "source": {
                            "page": 2,
                            "section": "Privacy",
                            "evidence": (
                                "Project data remains private."
                            ),
                        },
                    }
                ],
                "requirements": [],
                "decisions": [],
                "risks": [],
                "deadlines": [],
                "action_items": [],
                "missing_information": [],
            }
        ),
        source_fingerprint="analysis-fingerprint",
    )

    question = DocumentQuestion(
        document_id=document.id,
        user_id=user_id,
        question="How is project data protected?",
        answer=(
            "Project data remains private by default. "
            "[Source 1]"
        ),
        sources_json=json.dumps(
            [
                {
                    "source_id": 1,
                    "page": 2,
                    "section": "Privacy",
                    "evidence": (
                        "Project data remains private."
                    ),
                    "preview_type": "focused",
                }
            ]
        ),
        provider="gemini",
        model="test-model",
        status="Completed",
        source_fingerprint="question-fingerprint",
    )

    db.session.add_all(
        [
            analysis,
            question,
        ]
    )

    db.session.commit()

    return document


def test_document_library_renders_phase2_controls(
    app,
    client,
    user,
):
    with app.app_context():
        create_document_workspace(
            user_id=user
        )

    login(client)

    response = client.get(
        "/documents/"
    )

    assert response.status_code == 200

    page = response.get_data(
        as_text=True
    )

    assert "Turn every PDF into a searchable" in page
    assert "data-db-upload-form" in page
    assert "data-db-document-search" in page
    assert "data-db-status-filter" in page
    assert "data-db-view=\"grid\"" in page
    assert "Product Requirements.pdf" in page
    assert "document-brain-ui.js" in page


def test_document_details_renders_tabs_and_grounded_history(
    app,
    client,
    user,
):
    with app.app_context():
        document = create_document_workspace(
            user_id=user
        )

        document_id = document.id

    login(client)

    response = client.get(
        f"/documents/{document_id}"
    )

    assert response.status_code == 200

    page = response.get_data(
        as_text=True
    )

    assert "data-db-tab=\"overview\"" in page
    assert "data-db-tab=\"insights\"" in page
    assert "data-db-tab=\"actions\"" in page
    assert "data-db-tab=\"ask\"" in page
    assert "data-db-question-input" in page
    assert "data-db-question-search" in page
    assert "data-db-copy-target" in page
    assert "Focused excerpt" in page
    assert "Project data remains private." in page
