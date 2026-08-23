"""Step 13D/F trusted comparison persistence tests."""

from types import SimpleNamespace

from database import db
from models import (
    Document,
    DocumentComparison,
    Project,
)
from services import document_comparison_workflow_service as workflow
from services.document_comparison_verifier_service import (
    DocumentComparisonVerificationValidationError,
    VerifiedComparisonResult,
)


def _documents(user):
    project = Project(
        user_id=user,
        title="Comparison project",
    )

    document_a = Document(
        project=project,
        filename="a.pdf",
        file_path="a.pdf",
        extracted_text="Old rule.",
    )

    document_b = Document(
        project=project,
        filename="b.pdf",
        file_path="b.pdf",
        extracted_text="New rule.",
    )

    db.session.add_all(
        [
            project,
            document_a,
            document_b,
        ]
    )
    db.session.commit()

    return document_a, document_b


def _draft(document_a, document_b):
    foundation = SimpleNamespace(
        document_a=document_a,
        document_b=document_b,
        source_fingerprint="f" * 64,
        reusable_comparison=None,
    )

    return SimpleNamespace(
        foundation=foundation,
        candidates=SimpleNamespace(),
        alignment_hints=[],
        comparison={
            "summary": "Generated.",
            "findings": [
                {
                    "category": "changed",
                }
            ],
        },
        provider="test",
        model="comparison-model",
        reused_existing=False,
    )


def test_verified_comparison_is_saved_completed(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document_a, document_b = _documents(user)

        monkeypatch.setattr(
            workflow,
            "generate_owned_document_comparison_draft",
            lambda **kwargs: _draft(
                document_a,
                document_b,
            ),
        )

        verified_finding = {
            "category": "changed",
            "topic": "Rule",
            "explanation": "The rule changed.",
            "confidence": "High",
            "document_a": {
                "statement": "Old rule",
                "sources": [],
            },
            "document_b": {
                "statement": "New rule",
                "sources": [],
            },
        }

        monkeypatch.setattr(
            workflow,
            "verify_document_comparison_draft",
            lambda **kwargs: VerifiedComparisonResult(
                summary="LifeOS verified 1 material difference: 1 changed.",
                findings=[verified_finding],
                verifier_provider="test",
                verifier_model="verifier-model",
                rejected_findings=0,
            ),
        )

        result = workflow.compare_owned_documents(
            owner_id=user,
            document_a_id=document_a.id,
            document_b_id=document_b.id,
        )

        assert result.reused_existing is False
        assert result.comparison.status == "Completed"
        assert result.comparison.document_a_id == document_a.id
        assert result.comparison.document_b_id == document_b.id
        assert result.comparison.findings[0]["topic"] == "Rule"


def test_verification_failure_is_saved_failed_not_completed(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document_a, document_b = _documents(user)

        monkeypatch.setattr(
            workflow,
            "generate_owned_document_comparison_draft",
            lambda **kwargs: _draft(
                document_a,
                document_b,
            ),
        )

        monkeypatch.setattr(
            workflow,
            "verify_document_comparison_draft",
            lambda **kwargs: (_ for _ in ()).throw(
                DocumentComparisonVerificationValidationError(
                    "Unsupported comparison."
                )
            ),
        )

        try:
            workflow.compare_owned_documents(
                owner_id=user,
                document_a_id=document_a.id,
                document_b_id=document_b.id,
            )
        except workflow.DocumentComparisonWorkflowError:
            pass
        else:
            raise AssertionError(
                "Verification failure must fail the comparison."
            )

        rows = DocumentComparison.query.all()

        assert len(rows) == 1
        assert rows[0].status == "Failed"
        assert rows[0].findings == []


def test_existing_completed_comparison_is_reused_without_verification(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document_a, document_b = _documents(user)

        existing = DocumentComparison(
            user_id=user,
            document_a_id=document_a.id,
            document_b_id=document_b.id,
            provider="test",
            model="cached",
            status="Completed",
            source_fingerprint="f" * 64,
            summary="Cached.",
            findings_json="[]",
        )
        db.session.add(existing)
        db.session.commit()

        draft = SimpleNamespace(
            foundation=SimpleNamespace(
                document_a=document_a,
                document_b=document_b,
                source_fingerprint="f" * 64,
                reusable_comparison=existing,
            ),
            candidates=None,
            alignment_hints=[],
            comparison={
                "summary": "Cached.",
                "findings": [],
            },
            provider="test",
            model="cached",
            reused_existing=True,
        )

        monkeypatch.setattr(
            workflow,
            "generate_owned_document_comparison_draft",
            lambda **kwargs: draft,
        )

        monkeypatch.setattr(
            workflow,
            "verify_document_comparison_draft",
            lambda **kwargs: (_ for _ in ()).throw(
                AssertionError(
                    "Reusable trusted comparison must not be reverified."
                )
            ),
        )

        result = workflow.compare_owned_documents(
            owner_id=user,
            document_a_id=document_a.id,
            document_b_id=document_b.id,
        )

        assert result.reused_existing is True
        assert result.comparison.id == existing.id
