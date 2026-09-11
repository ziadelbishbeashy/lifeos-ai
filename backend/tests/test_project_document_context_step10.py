"""Step 10 tests for trusted document findings in project context."""

import hashlib
import json

import pytest

from database import db
from models import (
    Document,
    DocumentAIAnalysis,
    Project,
    User,
)
from services.document_analysis_service import (
    DOCUMENT_ANALYSIS_SCHEMA_VERSION,
)
from services.workspace_context_service import (
    WorkspaceContextNotFoundError,
    build_project_context,
    build_project_documents_context,
)


def _new_user(*, name: str, email: str) -> User:
    item = User(name=name, email=email)
    item.set_password("StrongPass123!")
    db.session.add(item)
    db.session.commit()
    return item


def _fingerprint(
    text: str,
    *,
    confirmed_type_key: str | None = None,
) -> str:
    type_identity = confirmed_type_key or "legacy_unconfirmed"
    payload = (
        f"{DOCUMENT_ANALYSIS_SCHEMA_VERSION}\n"
        f"{type_identity}\n"
        f"{text.strip()}"
    )
    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()


def _analysis_payload():
    return {
        "document_type_key": "requirements_document",
        "document_type": "Requirements Document",
        "summary": "The project must ship a secure document workspace.",
        "purpose": "Define project requirements and delivery constraints.",
        "key_points": [
            {
                "title": "Secure document access",
                "detail": "Private PDFs require ownership checks.",
                "source": {
                    "page": 2,
                    "section": "Security",
                    "evidence": "All document requests require ownership checks.",
                },
            },
        ],
        "requirements": [
            {
                "requirement": "Protect every document route",
                "details": "Enforce ownership before serving content.",
                "source": {
                    "page": 2,
                    "section": "Security",
                    "evidence": "Verify the project owner before PDF access.",
                },
            },
        ],
        "decisions": [
            {
                "decision": "Use project-scoped document ownership",
                "reason": "Documents inherit access through their project.",
                "source": {
                    "page": 3,
                    "section": "Architecture",
                    "evidence": "Project ownership controls document access.",
                },
            },
        ],
        "risks": [
            {
                "risk": "Cross-user document exposure",
                "impact": "Private project data could leak.",
                "source": {
                    "page": 4,
                    "section": "Risks",
                    "evidence": "Missing ownership filters could expose files.",
                },
            },
        ],
        "deadlines": [
            {
                "date": "2026-08-20",
                "description": "Complete the secure document workspace.",
                "source": {
                    "page": 5,
                    "section": "Timeline",
                    "evidence": "Secure workspace due August 20.",
                },
            },
        ],
        "action_items": [
            {
                "title": "Add ownership regression tests",
                "description": "Cover private project document routes.",
                "priority": "High",
                "deadline": "2026-08-18",
                "tags": ["security", "documents"],
                "source": {
                    "page": 6,
                    "section": "Actions",
                    "evidence": "Add tests for private document access.",
                },
            },
        ],
        "missing_information": [],
        "type_specific": {},
        "type_metadata": {
            "confirmed_type_key": "requirements_document",
        },
    }


def test_project_context_exposes_current_structured_document_findings(
    app,
    user,
):
    with app.app_context():
        project = Project(
            user_id=user,
            title="LifeOS",
            status="In Progress",
            priority="High",
        )
        db.session.add(project)
        db.session.commit()

        document_text = (
            "--- Page 1 ---\n"
            "Current requirements text."
        )

        document = Document(
            project_id=project.id,
            filename="requirements.pdf",
            file_path="instance/storage/requirements.pdf",
            extracted_text=document_text,
            summary="Legacy document card summary.",
        )
        db.session.add(document)
        db.session.flush()

        payload = _analysis_payload()

        analysis = DocumentAIAnalysis(
            document_id=document.id,
            user_id=user,
            provider="test",
            model="test-model",
            status="Completed",
            document_type="Requirements Document",
            summary=payload["summary"],
            insights_json=json.dumps(payload),
            source_fingerprint=_fingerprint(
                document_text,
                confirmed_type_key="requirements_document",
            ),
        )
        db.session.add(analysis)
        db.session.commit()

        context = build_project_context(
            owner_id=user,
            project_id=project.id,
        )

        document_context = context["documents"][0]
        trusted = document_context["trusted_analysis"]

        assert document_context["analysis_status"] == "Current"
        assert document_context["has_current_analysis"] is True
        assert trusted["summary"] == payload["summary"]
        assert (
            trusted["requirements"][0]["text"]
            == "Protect every document route"
        )
        assert trusted["requirements"][0]["source"]["page"] == 2
        assert (
            trusted["decisions"][0]["text"]
            == "Use project-scoped document ownership"
        )
        assert (
            trusted["risks"][0]["text"]
            == "Cross-user document exposure"
        )
        assert trusted["deadlines"][0]["date"] == "2026-08-20"
        assert (
            trusted["action_items"][0]["title"]
            == "Add ownership regression tests"
        )

        counts = context["context_counts"]

        assert counts["documents_considered"] == 1
        assert counts["documents_with_current_analysis"] == 1
        assert counts["documents_with_stale_analysis"] == 0
        assert counts["document_findings_considered"] >= 6


def test_stale_document_analysis_is_not_exposed_as_trusted_project_truth(
    app,
    user,
):
    with app.app_context():
        project = Project(
            user_id=user,
            title="Changing Project",
        )
        db.session.add(project)
        db.session.commit()

        document = Document(
            project_id=project.id,
            filename="plan.pdf",
            file_path="instance/storage/plan.pdf",
            extracted_text="New changed document content.",
            summary="Potentially stale card summary.",
        )
        db.session.add(document)
        db.session.flush()

        payload = _analysis_payload()

        analysis = DocumentAIAnalysis(
            document_id=document.id,
            user_id=user,
            provider="test",
            model="test-model",
            status="Completed",
            document_type="Requirements Document",
            summary=payload["summary"],
            insights_json=json.dumps(payload),
            source_fingerprint=_fingerprint(
                "Old document content.",
                confirmed_type_key="requirements_document",
            ),
        )
        db.session.add(analysis)
        db.session.commit()

        context = build_project_context(
            owner_id=user,
            project_id=project.id,
        )

        document_context = context["documents"][0]

        assert document_context["analysis_status"] == "Stale"
        assert document_context["has_current_analysis"] is False
        assert document_context["trusted_analysis"] is None
        assert (
            context["context_counts"]["documents_with_stale_analysis"]
            == 1
        )
        assert (
            context["context_counts"]["document_findings_considered"]
            == 0
        )


def test_foreign_analysis_row_is_not_used(
    app,
    user,
):
    with app.app_context():
        foreign_user = _new_user(
            name="Foreign User",
            email="foreign-step10@example.com",
        )

        project = Project(
            user_id=user,
            title="Private Project",
        )
        db.session.add(project)
        db.session.commit()

        document_text = "Private current document."

        document = Document(
            project_id=project.id,
            filename="private.pdf",
            file_path="instance/storage/private.pdf",
            extracted_text=document_text,
        )
        db.session.add(document)
        db.session.flush()

        payload = _analysis_payload()

        analysis = DocumentAIAnalysis(
            document_id=document.id,
            user_id=foreign_user.id,
            provider="test",
            model="test-model",
            status="Completed",
            document_type="Requirements Document",
            summary=payload["summary"],
            insights_json=json.dumps(payload),
            source_fingerprint=_fingerprint(
                document_text,
                confirmed_type_key="requirements_document",
            ),
        )
        db.session.add(analysis)
        db.session.commit()

        context = build_project_context(
            owner_id=user,
            project_id=project.id,
        )

        document_context = context["documents"][0]

        assert document_context["analysis_status"] == "Not analysed"
        assert document_context["trusted_analysis"] is None


def test_direct_document_context_builder_enforces_project_ownership(
    app,
    user,
):
    with app.app_context():
        other_user = _new_user(
            name="Other Owner",
            email="other-owner-step10@example.com",
        )

        private_project = Project(
            user_id=other_user.id,
            title="Other User Project",
        )
        db.session.add(private_project)
        db.session.commit()

        with pytest.raises(
            WorkspaceContextNotFoundError
        ):
            build_project_documents_context(
                owner_id=user,
                project_id=private_project.id,
            )
