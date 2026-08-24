"""Rendering checks for the Phase 2 Document Brain interface."""

from __future__ import annotations

import json
from types import SimpleNamespace

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
                "questions": [
                    {
                        "question": (
                            "Which privacy controls are required?"
                        ),
                        "reason": (
                            "Review the document's security scope."
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
    assert "Structured sections" in page
    assert "Questions to explore" in page
    assert "Which privacy controls are required?" in page



def test_detect_type_route_renders_confirmation_panel(
    app,
    client,
    user,
    monkeypatch,
):
    from routes import document_routes

    with app.app_context():
        project = Project(
            user_id=user,
            title="Detection Project",
            status="In Progress",
            priority="Medium",
        )

        document = Document(
            project=project,
            filename="Research.pdf",
            file_path="stored/research.pdf",
            extracted_text=(
                "Abstract. Methodology. Results. Limitations."
            ),
        )

        db.session.add_all(
            [
                project,
                document,
            ]
        )
        db.session.commit()

        document_id = document.id

    fake_detection = SimpleNamespace(
        document_type_key="research_paper",
        document_type_label="Research Paper",
        confidence="high",
        reason=(
            "The document follows a research structure "
            "with methodology and results."
        ),
        provider="gemini",
        model="test-model",
    )

    monkeypatch.setattr(
        document_routes,
        "detect_owned_document_type",
        lambda **kwargs: SimpleNamespace(
            document=Document.query.get(
                kwargs["document_id"]
            ),
            detection=fake_detection,
        ),
    )

    login(client)

    response = client.post(
        f"/documents/{document_id}/detect-type",
        data={},
    )

    assert response.status_code == 200

    page = response.get_data(
        as_text=True
    )

    assert "data-db-type-confirmation" in page
    assert "LifeOS detected" in page
    assert "Research Paper" in page
    assert "High" in page
    assert "Confirm and analyse" in page
    assert 'name="confirmed_document_type"' in page
    assert 'value="research_paper"' in page
    assert "Detect again" in page


def test_document_details_starts_with_type_detection_action(
    app,
    client,
    user,
):
    with app.app_context():
        project = Project(
            user_id=user,
            title="Fresh PDF Project",
            status="In Progress",
            priority="Medium",
        )

        document = Document(
            project=project,
            filename="Fresh.pdf",
            file_path="stored/fresh.pdf",
            extracted_text="Readable PDF content.",
        )

        db.session.add_all(
            [
                project,
                document,
            ]
        )
        db.session.commit()

        document_id = document.id

    login(client)

    response = client.get(
        f"/documents/{document_id}"
    )

    page = response.get_data(
        as_text=True
    )

    assert response.status_code == 200
    assert "Detect document type" in page
    assert (
        f"/documents/{document_id}/detect-type"
        in page
    )
    assert "data-db-type-confirmation" not in page


def test_type_confirmation_includes_all_supported_choices(
    app,
    client,
    user,
    monkeypatch,
):
    from routes import document_routes

    with app.app_context():
        project = Project(
            user_id=user,
            title="Types Project",
            status="In Progress",
            priority="Medium",
        )

        document = Document(
            project=project,
            filename="Mixed.pdf",
            file_path="stored/mixed.pdf",
            extracted_text="Readable content.",
        )

        db.session.add_all(
            [
                project,
                document,
            ]
        )
        db.session.commit()

        document_id = document.id

    fake_detection = SimpleNamespace(
        document_type_key="general_reference",
        document_type_label="General Reference",
        confidence="low",
        reason="No specialized type clearly fits.",
        provider="gemini",
        model="test-model",
    )

    monkeypatch.setattr(
        document_routes,
        "detect_owned_document_type",
        lambda **kwargs: SimpleNamespace(
            document=Document.query.get(
                kwargs["document_id"]
            ),
            detection=fake_detection,
        ),
    )

    login(client)

    response = client.post(
        f"/documents/{document_id}/detect-type",
        data={},
    )

    page = response.get_data(
        as_text=True
    )

    for label in (
        "Requirements Document",
        "Research Paper",
        "Meeting Notes",
        "Project Plan",
        "Technical Documentation",
        "Lecture Material",
        "Policy",
        "Contract",
        "General Reference",
    ):
        assert label in page


def test_invalid_confirmed_type_is_rejected_before_analysis(
    app,
    client,
    user,
    monkeypatch,
):
    from routes import document_routes

    with app.app_context():
        project = Project(
            user_id=user,
            title="Invalid Type Project",
            status="In Progress",
            priority="Medium",
        )

        document = Document(
            project=project,
            filename="Invalid.pdf",
            file_path="stored/invalid.pdf",
            extracted_text="Readable content.",
        )

        db.session.add_all(
            [
                project,
                document,
            ]
        )
        db.session.commit()

        document_id = document.id

    called = {
        "analysis": False,
    }

    def fake_analyse(**kwargs):
        called["analysis"] = True
        raise AssertionError(
            "Analysis must not run for an invalid type."
        )

    monkeypatch.setattr(
        document_routes,
        "analyse_owned_document",
        fake_analyse,
    )

    login(client)

    response = client.post(
        f"/documents/{document_id}/analyse",
        data={
            "confirmed_document_type": "financial_report",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert called["analysis"] is False
