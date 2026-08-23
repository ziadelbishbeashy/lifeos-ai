"""Step 13C semantic-alignment tests."""

from types import SimpleNamespace

from services.document_comparison_candidate_service import (
    ComparisonEvidence,
    DocumentCandidateCoverage,
    DocumentComparisonCandidateBundle,
)
from services import document_comparison_alignment_service as alignment


def _evidence(source_id, side, text, kind="requirement"):
    return ComparisonEvidence(
        source_id=source_id,
        side=side,
        document_id=1 if side == "A" else 2,
        filename="a.pdf" if side == "A" else "b.pdf",
        kind=kind,
        topic=text,
        statement=text,
        detail="",
        page=1,
        section="",
        evidence=text,
        origin="structured_analysis",
    )


def _bundle(a_text, b_text):
    coverage_a = DocumentCandidateCoverage(
        document_id=1,
        filename="a.pdf",
        analysis_status="Current",
        analysis_id=1,
        structured_evidence_count=1,
        chunk_evidence_count=0,
        mode="structured_only",
        truncated=False,
    )

    coverage_b = DocumentCandidateCoverage(
        document_id=2,
        filename="b.pdf",
        analysis_status="Current",
        analysis_id=2,
        structured_evidence_count=1,
        chunk_evidence_count=0,
        mode="structured_only",
        truncated=False,
    )

    return DocumentComparisonCandidateBundle(
        document_a=SimpleNamespace(id=1, filename="a.pdf"),
        document_b=SimpleNamespace(id=2, filename="b.pdf"),
        evidence_a=[_evidence("A1", "A", a_text)],
        evidence_b=[_evidence("B1", "B", b_text)],
        coverage_a=coverage_a,
        coverage_b=coverage_b,
    )


def test_lexical_alignment_pairs_related_requirements():
    bundle = _bundle(
        "Users must authenticate before document access.",
        "Users must authenticate before private document access.",
    )

    hints = alignment.align_comparison_candidates(
        bundle,
        use_semantic=False,
    )

    assert len(hints) == 1
    assert hints[0].source_a_id == "A1"
    assert hints[0].source_b_id == "B1"


def test_semantic_paraphrase_can_create_alignment_hint(monkeypatch):
    bundle = _bundle(
        "Prevent one account from reading another user's PDFs.",
        "Enforce ownership authorization for private documents.",
    )

    monkeypatch.setattr(
        alignment,
        "_semantic_enabled",
        lambda: True,
    )

    monkeypatch.setattr(
        alignment,
        "_semantic_pair_scores",
        lambda bundle: {
            ("A1", "B1"): 0.89,
        },
    )

    hints = alignment.align_comparison_candidates(bundle)

    assert len(hints) == 1
    assert hints[0].method == "semantic"
    assert hints[0].score >= 0.89


def test_alignment_context_hides_similarity_scores():
    context = alignment.build_alignment_hint_context(
        [
            alignment.ComparisonAlignmentHint(
                source_a_id="A1",
                source_b_id="B3",
                score=0.9342,
                method="semantic",
            )
        ]
    )

    assert "A1" in context
    assert "B3" in context
    assert "0.9342" not in context
    assert "semantic" not in context.casefold()
