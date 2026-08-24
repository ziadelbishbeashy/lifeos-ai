"""Rendering tests for the Step 6E adaptive analysis dashboard."""

import json

from database import db
from models import (
    Document,
    DocumentAIAnalysis,
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


def test_research_analysis_renders_specialized_workspace(
    app,
    client,
    user,
):
    with app.app_context():
        project = Project(
            user_id=user,
            title="Research Project",
            status="In Progress",
            priority="Medium",
        )

        document = Document(
            project=project,
            filename="paper.pdf",
            file_path="stored/paper.pdf",
            extracted_text="Research paper content.",
        )

        db.session.add_all(
            [project, document]
        )
        db.session.commit()

        analysis = DocumentAIAnalysis(
            document_id=document.id,
            user_id=user,
            provider="gemini",
            model="test-model",
            status="Completed",
            document_type="Research Paper",
            summary="A grounded retrieval research study.",
            insights_json=json.dumps(
                {
                    "document_type_key": "research_paper",
                    "document_type": "Research Paper",
                    "summary": "A grounded retrieval research study.",
                    "purpose": "Evaluate retrieval quality.",
                    "key_points": [],
                    "requirements": [],
                    "decisions": [],
                    "risks": [],
                    "deadlines": [],
                    "action_items": [],
                    "missing_information": [],
                    "questions": [],
                    "type_metadata": {
                        "detected_type_key": "research_paper",
                        "detected_type": "Research Paper",
                        "confirmed_type_key": "research_paper",
                        "confirmed_type": "Research Paper",
                        "source": "detected_confirmed",
                        "confidence": "high",
                    },
                    "type_specific": {
                        "research_problem": {
                            "text": "Grounding failures reduce answer reliability.",
                            "source": {
                                "page": 2,
                                "section": "Introduction",
                                "evidence": "Grounding failures reduce reliability.",
                            },
                        },
                        "objectives": [],
                        "methodology": [
                            {
                                "text": "Hybrid retrieval evaluation",
                                "detail": "BM25 and semantic retrieval are compared.",
                                "source": {
                                    "page": 4,
                                    "section": "Method",
                                    "evidence": "We compare BM25 and semantic retrieval.",
                                },
                            }
                        ],
                        "dataset_or_participants": [],
                        "findings": [],
                        "limitations": [],
                        "research_gaps": [],
                        "future_work": [],
                    },
                }
            ),
            source_fingerprint="research-type-aware",
        )

        db.session.add(
            analysis
        )
        db.session.commit()

        document_id = document.id

    login(
        client
    )

    response = client.get(
        f"/documents/{document_id}"
    )

    assert response.status_code == 200

    page = response.get_data(
        as_text=True
    )

    assert "Type-aware analysis" in page
    assert "Research Paper workspace" in page
    assert "Detected and confirmed" in page
    assert "Research Problem" in page
    assert "Methodology" in page
    assert "Research Gaps" in page
    assert "Grounding failures reduce answer reliability." in page
    assert "Hybrid retrieval evaluation" in page
    assert "Adaptive workspace" in page


def test_user_override_message_is_rendered(
    app,
    client,
    user,
):
    with app.app_context():
        project = Project(
            user_id=user,
            title="Override Project",
            status="In Progress",
            priority="Medium",
        )

        document = Document(
            project=project,
            filename="mixed.pdf",
            file_path="stored/mixed.pdf",
            extracted_text="Mixed technical and academic content.",
        )

        db.session.add_all(
            [project, document]
        )
        db.session.commit()

        analysis = DocumentAIAnalysis(
            document_id=document.id,
            user_id=user,
            provider="gemini",
            model="test-model",
            status="Completed",
            document_type="Research Paper",
            summary="User-confirmed research analysis.",
            insights_json=json.dumps(
                {
                    "document_type_key": "research_paper",
                    "document_type": "Research Paper",
                    "summary": "User-confirmed research analysis.",
                    "type_metadata": {
                        "detected_type_key": "technical_documentation",
                        "detected_type": "Technical Documentation",
                        "confirmed_type_key": "research_paper",
                        "confirmed_type": "Research Paper",
                        "source": "user_override",
                        "confidence": "medium",
                    },
                    "type_specific": {},
                }
            ),
            source_fingerprint="override-type-aware",
        )

        db.session.add(
            analysis
        )
        db.session.commit()

        document_id = document.id

    login(
        client
    )

    response = client.get(
        f"/documents/{document_id}"
    )

    page = response.get_data(
        as_text=True
    )

    assert "User override applied." in page
    assert "Technical Documentation" in page
    assert "Research Paper" in page
