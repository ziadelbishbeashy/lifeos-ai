"""Step 13D final comparison workflow.

This is the trusted persistence boundary for Step 13.

A new DocumentComparison becomes Completed only after:
1. Step 13A validates ownership/order/fingerprint.
2. Step 13B builds trusted evidence.
3. Step 13C generates a normalized semantic comparison draft.
4. Step 13D verifies every persisted finding against the exact cited evidence.

Failed generation/verification is stored as Failed for troubleshooting but is
never reusable as trusted comparison output.
"""

from __future__ import annotations

from dataclasses import dataclass
import json

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import DocumentComparison
from services.document_comparison_draft_service import (
    DocumentComparisonDraftError,
    generate_owned_document_comparison_draft,
)
from services.document_comparison_verifier_service import (
    DocumentComparisonVerificationError,
    verify_document_comparison_draft,
)


class DocumentComparisonWorkflowError(RuntimeError):
    """Raised when a trusted comparison cannot be completed."""


class DocumentComparisonPersistenceError(
    DocumentComparisonWorkflowError
):
    """Raised when the comparison result cannot be saved."""


@dataclass(frozen=True)
class SavedDocumentComparison:
    """Trusted saved comparison result."""

    comparison: DocumentComparison
    reused_existing: bool
    rejected_findings: int = 0


def compare_owned_documents(
    *,
    owner_id: int,
    document_a_id: int,
    document_b_id: int,
    force: bool = False,
    use_semantic_alignment: bool = True,
) -> SavedDocumentComparison:
    """Generate, verify, and persist one ordered A -> B comparison."""

    try:
        draft = generate_owned_document_comparison_draft(
            owner_id=owner_id,
            document_a_id=document_a_id,
            document_b_id=document_b_id,
            force=force,
            use_semantic_alignment=use_semantic_alignment,
        )

    except DocumentComparisonDraftError as error:
        raise DocumentComparisonWorkflowError(
            str(error)
        ) from error

    if draft.reused_existing:
        existing = (
            draft.foundation.reusable_comparison
        )

        if existing is None:
            raise DocumentComparisonWorkflowError(
                "LifeOS could not load the reusable comparison."
            )

        return SavedDocumentComparison(
            comparison=existing,
            reused_existing=True,
        )

    if draft.candidates is None:
        raise DocumentComparisonWorkflowError(
            "LifeOS did not prepare comparison evidence."
        )

    try:
        verified = verify_document_comparison_draft(
            bundle=draft.candidates,
            comparison=draft.comparison,
        )

    except DocumentComparisonVerificationError as error:
        _save_failed_comparison(
            owner_id=owner_id,
            document_a_id=draft.foundation.document_a.id,
            document_b_id=draft.foundation.document_b.id,
            source_fingerprint=draft.foundation.source_fingerprint,
            provider=draft.provider,
            model=draft.model,
            error=error,
        )

        raise DocumentComparisonWorkflowError(
            str(error)
        ) from error

    # Another request may have completed this exact comparison while this
    # request was generating/verifying. Reuse it instead of adding noise.
    existing = (
        DocumentComparison.query
        .filter_by(
            user_id=owner_id,
            document_a_id=draft.foundation.document_a.id,
            document_b_id=draft.foundation.document_b.id,
            status="Completed",
            source_fingerprint=draft.foundation.source_fingerprint,
        )
        .order_by(
            DocumentComparison.created_at.desc(),
            DocumentComparison.id.desc(),
        )
        .first()
    )

    if existing is not None:
        return SavedDocumentComparison(
            comparison=existing,
            reused_existing=True,
        )

    comparison = DocumentComparison(
        user_id=owner_id,
        document_a_id=draft.foundation.document_a.id,
        document_b_id=draft.foundation.document_b.id,
        summary=verified.summary,
        findings_json=json.dumps(
            verified.findings,
            ensure_ascii=False,
        ),
        provider=draft.provider,
        model=draft.model,
        status="Completed",
        source_fingerprint=(
            draft.foundation.source_fingerprint
        ),
        error_message=None,
    )

    try:
        db.session.add(
            comparison
        )
        db.session.commit()

    except SQLAlchemyError as error:
        db.session.rollback()

        raise DocumentComparisonPersistenceError(
            "LifeOS could not save the verified document comparison."
        ) from error

    return SavedDocumentComparison(
        comparison=comparison,
        reused_existing=False,
        rejected_findings=verified.rejected_findings,
    )


def _save_failed_comparison(
    *,
    owner_id: int,
    document_a_id: int,
    document_b_id: int,
    source_fingerprint: str,
    provider: str,
    model: str,
    error: Exception,
) -> None:
    failed = DocumentComparison(
        user_id=owner_id,
        document_a_id=document_a_id,
        document_b_id=document_b_id,
        summary=None,
        findings_json=None,
        provider=(
            str(
                provider
                or "lifeos"
            )[:30]
        ),
        model=(
            str(
                model
                or "comparison"
            )[:100]
        ),
        status="Failed",
        source_fingerprint=source_fingerprint,
        error_message=(
            " ".join(
                str(
                    error
                ).split()
            )[:4_000]
        ),
    )

    try:
        db.session.add(
            failed
        )
        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()
