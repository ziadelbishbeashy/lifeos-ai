"""Step 13B+C orchestration for an unverified two-document comparison draft.

This service connects:
- Step 13A ownership / ordered pair / cache identity
- Step 13B evidence registry
- Step 13C semantic alignment and AI classification

Important trust boundary:
The generated findings are NOT persisted as Completed here. Step 13D will
verify source support before a new comparison becomes reusable trusted data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.ai_service import (
    AIServiceError,
    compare_document_evidence,
)
from services.document_comparison_alignment_service import (
    ComparisonAlignmentHint,
    align_comparison_candidates,
    build_alignment_hint_context,
)
from services.document_comparison_candidate_service import (
    DocumentComparisonCandidateBundle,
    DocumentComparisonCandidateError,
    build_comparison_evidence_context,
    build_owned_document_comparison_candidates,
)
from services.document_comparison_service import (
    DocumentComparisonFoundation,
    prepare_owned_document_comparison,
)


class DocumentComparisonDraftError(RuntimeError):
    """Raised when Step 13B+C cannot generate a comparison draft."""


@dataclass(frozen=True)
class GeneratedDocumentComparisonDraft:
    """A normalized but not-yet-evidence-verified comparison."""

    foundation: DocumentComparisonFoundation
    candidates: DocumentComparisonCandidateBundle | None
    alignment_hints: list[ComparisonAlignmentHint]
    comparison: dict[str, Any]
    provider: str
    model: str
    reused_existing: bool


def generate_owned_document_comparison_draft(
    *,
    owner_id: int,
    document_a_id: int,
    document_b_id: int,
    force: bool = False,
    use_semantic_alignment: bool = True,
) -> GeneratedDocumentComparisonDraft:
    """Generate or reuse an ordered A -> B comparison draft."""

    foundation = prepare_owned_document_comparison(
        owner_id=owner_id,
        document_a_id=document_a_id,
        document_b_id=document_b_id,
        force=force,
    )

    if foundation.reusable_comparison is not None:
        saved = foundation.reusable_comparison

        return GeneratedDocumentComparisonDraft(
            foundation=foundation,
            candidates=None,
            alignment_hints=[],
            comparison={
                "summary": saved.summary or "",
                "findings": saved.findings,
            },
            provider=saved.provider,
            model=saved.model,
            reused_existing=True,
        )

    try:
        candidates = (
            build_owned_document_comparison_candidates(
                owner_id=owner_id,
                document_a_id=foundation.document_a.id,
                document_b_id=foundation.document_b.id,
            )
        )

        alignment_hints = align_comparison_candidates(
            candidates,
            use_semantic=use_semantic_alignment,
        )

        evidence_context = build_comparison_evidence_context(
            candidates
        )

        alignment_context = build_alignment_hint_context(
            alignment_hints
        )

        result = compare_document_evidence(
            document_a_filename=foundation.document_a.filename,
            document_b_filename=foundation.document_b.filename,
            evidence_context=evidence_context,
            alignment_context=alignment_context,
        )

    except (
        DocumentComparisonCandidateError,
        AIServiceError,
    ) as error:
        raise DocumentComparisonDraftError(
            str(error)
        ) from error

    return GeneratedDocumentComparisonDraft(
        foundation=foundation,
        candidates=candidates,
        alignment_hints=alignment_hints,
        comparison=result["comparison"],
        provider=str(
            result.get("provider")
            or "unknown"
        )[:30],
        model=str(
            result.get("model")
            or "unknown"
        )[:100],
        reused_existing=False,
    )
