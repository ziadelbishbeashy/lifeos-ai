"""Step 13B+C draft orchestration tests."""

from types import SimpleNamespace

from services import document_comparison_draft_service as workflow


def test_draft_workflow_connects_candidates_alignment_and_ai(monkeypatch):
    foundation = SimpleNamespace(
        document_a=SimpleNamespace(
            id=10,
            filename="a.pdf",
        ),
        document_b=SimpleNamespace(
            id=20,
            filename="b.pdf",
        ),
        reusable_comparison=None,
    )

    candidates = SimpleNamespace(
        document_a=foundation.document_a,
        document_b=foundation.document_b,
    )

    monkeypatch.setattr(
        workflow,
        "prepare_owned_document_comparison",
        lambda **kwargs: foundation,
    )

    monkeypatch.setattr(
        workflow,
        "build_owned_document_comparison_candidates",
        lambda **kwargs: candidates,
    )

    monkeypatch.setattr(
        workflow,
        "align_comparison_candidates",
        lambda *args, **kwargs: [],
    )

    monkeypatch.setattr(
        workflow,
        "build_comparison_evidence_context",
        lambda candidates: "[A1] old\n[B1] new",
    )

    monkeypatch.setattr(
        workflow,
        "build_alignment_hint_context",
        lambda hints: "No hints",
    )

    monkeypatch.setattr(
        workflow,
        "compare_document_evidence",
        lambda **kwargs: {
            "provider": "test",
            "model": "comparison-model",
            "comparison": {
                "summary": "One change.",
                "findings": [
                    {
                        "category": "changed",
                    }
                ],
            },
        },
    )

    result = workflow.generate_owned_document_comparison_draft(
        owner_id=1,
        document_a_id=10,
        document_b_id=20,
    )

    assert result.reused_existing is False
    assert result.provider == "test"
    assert result.comparison["summary"] == "One change."


def test_draft_workflow_reuses_verified_completed_comparison(monkeypatch):
    saved = SimpleNamespace(
        summary="Cached verified comparison.",
        findings=[
            {
                "category": "changed",
            }
        ],
        provider="test",
        model="cached-model",
    )

    foundation = SimpleNamespace(
        document_a=SimpleNamespace(
            id=10,
            filename="a.pdf",
        ),
        document_b=SimpleNamespace(
            id=20,
            filename="b.pdf",
        ),
        reusable_comparison=saved,
    )

    monkeypatch.setattr(
        workflow,
        "prepare_owned_document_comparison",
        lambda **kwargs: foundation,
    )

    monkeypatch.setattr(
        workflow,
        "build_owned_document_comparison_candidates",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "Candidates must not be rebuilt for a reusable comparison."
            )
        ),
    )

    result = workflow.generate_owned_document_comparison_draft(
        owner_id=1,
        document_a_id=10,
        document_b_id=20,
    )

    assert result.reused_existing is True
    assert result.candidates is None
    assert result.comparison["summary"] == "Cached verified comparison."
