"""Step 13D/F fail-closed comparison verification tests."""

from types import SimpleNamespace

import pytest

from services.document_comparison_candidate_service import (
    ComparisonEvidence,
    DocumentCandidateCoverage,
    DocumentComparisonCandidateBundle,
)
from services import document_comparison_verifier_service as verifier


def _coverage(
    *,
    document_id,
    filename,
    status="Current",
    mode="structured_plus_chunks",
    structured=2,
    chunks=1,
    truncated=False,
):
    return DocumentCandidateCoverage(
        document_id=document_id,
        filename=filename,
        analysis_status=status,
        analysis_id=1 if status == "Current" else None,
        structured_evidence_count=structured,
        chunk_evidence_count=chunks,
        mode=mode,
        truncated=truncated,
    )


def _evidence(
    source_id,
    side,
    *,
    document_id,
    filename,
    text,
    page,
):
    return ComparisonEvidence(
        source_id=source_id,
        side=side,
        document_id=document_id,
        filename=filename,
        kind="requirement",
        topic="Password policy",
        statement=text,
        detail="",
        page=page,
        section="Security",
        evidence=text,
        origin="structured_analysis",
        chunk_id=document_id * 100 + page,
        chunk_index=page - 1,
    )


def _bundle(
    *,
    coverage_a=None,
    coverage_b=None,
):
    evidence_a = _evidence(
        "A1",
        "A",
        document_id=10,
        filename="a.pdf",
        text="Minimum password length is eight.",
        page=2,
    )

    evidence_b = _evidence(
        "B1",
        "B",
        document_id=20,
        filename="b.pdf",
        text="Minimum password length is twelve.",
        page=4,
    )

    return DocumentComparisonCandidateBundle(
        document_a=SimpleNamespace(
            id=10,
            filename="a.pdf",
        ),
        document_b=SimpleNamespace(
            id=20,
            filename="b.pdf",
        ),
        evidence_a=[evidence_a],
        evidence_b=[evidence_b],
        coverage_a=(
            coverage_a
            or _coverage(
                document_id=10,
                filename="a.pdf",
            )
        ),
        coverage_b=(
            coverage_b
            or _coverage(
                document_id=20,
                filename="b.pdf",
            )
        ),
    )


def _changed_draft(
    *,
    a_sources=None,
    b_sources=None,
):
    return {
        "summary": "Password length changed.",
        "findings": [
            {
                "category": "changed",
                "topic": "Password policy",
                "explanation": (
                    "The minimum password length changed from eight to twelve."
                ),
                "confidence": "High",
                "document_a": {
                    "statement": "Minimum 8",
                    "source_ids": (
                        ["A1"]
                        if a_sources is None
                        else a_sources
                    ),
                },
                "document_b": {
                    "statement": "Minimum 12",
                    "source_ids": (
                        ["B1"]
                        if b_sources is None
                        else b_sources
                    ),
                },
            }
        ],
    }


def test_unknown_source_ids_fail_closed_before_provider(monkeypatch):
    called = {
        "provider": False,
    }

    monkeypatch.setattr(
        verifier,
        "get_ai_configuration",
        lambda: called.update(
            provider=True
        ),
    )

    with pytest.raises(
        verifier.DocumentComparisonVerificationValidationError
    ):
        verifier.verify_document_comparison_draft(
            bundle=_bundle(),
            comparison=_changed_draft(
                a_sources=["A99"],
            ),
        )

    assert called["provider"] is False


def test_added_claim_requires_complete_current_baseline_coverage():
    chunk_only_a = _coverage(
        document_id=10,
        filename="a.pdf",
        status="Not analysed",
        mode="chunks_only",
        structured=0,
        chunks=10,
        truncated=False,
    )

    draft = {
        "summary": "New requirement.",
        "findings": [
            {
                "category": "added",
                "topic": "Password policy",
                "explanation": "B adds a password rule.",
                "confidence": "High",
                "document_a": {
                    "statement": "",
                    "source_ids": [],
                },
                "document_b": {
                    "statement": "Minimum 12",
                    "source_ids": ["B1"],
                },
            }
        ],
    }

    with pytest.raises(
        verifier.DocumentComparisonVerificationValidationError
    ):
        verifier.verify_document_comparison_draft(
            bundle=_bundle(
                coverage_a=chunk_only_a,
            ),
            comparison=draft,
        )


def test_high_confidence_verifier_accepts_and_copies_trusted_sources(
    monkeypatch,
):
    monkeypatch.setattr(
        verifier,
        "get_ai_configuration",
        lambda: {
            "provider": "test",
            "api_key": "key",
            "model": "verifier-model",
        },
    )

    monkeypatch.setattr(
        verifier,
        "route_ai_text",
        lambda **kwargs: (
            '{"decisions":['
            '{"finding_index":1,'
            '"supported":true,'
            '"confidence":"high",'
            '"reason":"Both sources directly support the material change."}'
            ']}'
        ),
    )

    result = verifier.verify_document_comparison_draft(
        bundle=_bundle(),
        comparison=_changed_draft(),
    )

    assert len(result.findings) == 1

    finding = result.findings[0]

    assert finding["category"] == "changed"
    assert finding["document_a"]["sources"][0]["filename"] == "a.pdf"
    assert finding["document_a"]["sources"][0]["page"] == 2
    assert finding["document_b"]["sources"][0]["filename"] == "b.pdf"
    assert finding["document_b"]["sources"][0]["page"] == 4

    # Backend provenance is retained for future audits/navigation.
    assert finding["document_a"]["sources"][0]["chunk_id"] is not None


def test_medium_confidence_verifier_is_rejected(monkeypatch):
    monkeypatch.setattr(
        verifier,
        "get_ai_configuration",
        lambda: {
            "provider": "test",
            "api_key": "key",
            "model": "verifier-model",
        },
    )

    monkeypatch.setattr(
        verifier,
        "route_ai_text",
        lambda **kwargs: (
            '{"decisions":['
            '{"finding_index":1,'
            '"supported":true,'
            '"confidence":"medium",'
            '"reason":"Uncertain."}'
            ']}'
        ),
    )

    with pytest.raises(
        verifier.DocumentComparisonVerificationValidationError
    ):
        verifier.verify_document_comparison_draft(
            bundle=_bundle(),
            comparison=_changed_draft(),
        )


def test_empty_draft_returns_safe_available_evidence_summary():
    result = verifier.verify_document_comparison_draft(
        bundle=_bundle(),
        comparison={
            "summary": "Documents are identical.",
            "findings": [],
        },
    )

    assert result.findings == []
    assert "available comparison evidence" in result.summary
    assert "identical" not in result.summary.casefold()
