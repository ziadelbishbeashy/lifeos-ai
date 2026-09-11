"""Regression guards for Step 11 compatibility with Step 9 callers."""

from services.document_task_suggestion_service import (
    MATCH_THRESHOLD,
    _normalise_match_text,
    calculate_task_match_score,
)
from services.task_duplicate_service import (
    DUPLICATE_OVERALL_THRESHOLD,
)


def test_match_threshold_public_api_is_preserved():
    assert MATCH_THRESHOLD == DUPLICATE_OVERALL_THRESHOLD


def test_existing_step9_similarity_contract_still_passes():
    score = calculate_task_match_score(
        "Build secure PDF upload",
        "Implement secure PDF upload",
    )

    assert score >= MATCH_THRESHOLD


def test_generated_suggestion_title_normaliser_still_exists():
    assert (
        _normalise_match_text(
            "  Build Secure PDF Upload! "
        )
        == "build secure pdf upload"
    )
