"""Consolidated Step 11 regression tests."""

from types import SimpleNamespace

from services import task_duplicate_service as duplicate


def _task(
    task_id: int,
    title: str,
    description: str = "",
    status: str = "Pending",
):
    return SimpleNamespace(
        id=task_id,
        title=title,
        description=description,
        status=status,
    )


def test_strong_semantic_candidate_is_not_hidden_by_higher_blended_nonduplicate(
    monkeypatch,
):
    monkeypatch.setattr(
        duplicate,
        "_semantic_similarity_scores",
        lambda **kwargs: [
            0.93,
            0.10,
        ],
    )

    assessment = duplicate.assess_task_duplicate(
        suggestion_title="Protect private project files",
        suggestion_description="Prevent cross-account access to PDFs.",
        existing_tasks=[
            _task(
                1,
                "Enforce document authorization",
                "Check ownership for private files.",
            ),
            _task(
                2,
                "Project file review",
                "Review PDFs before release.",
            ),
        ],
    )

    assert assessment.is_duplicate is True
    assert assessment.matched_task.id == 1
    assert assessment.semantic_score == 0.93


def test_no_duplicate_returns_create_new_even_with_partial_overlap(
    monkeypatch,
):
    monkeypatch.setattr(
        duplicate,
        "_semantic_similarity_scores",
        lambda **kwargs: [0.40],
    )

    assessment = duplicate.assess_task_duplicate(
        suggestion_title="Prepare festival presentation",
        suggestion_description="Create slides for the final presentation.",
        existing_tasks=[
            _task(
                5,
                "Prepare release notes",
                "Document the software release.",
            ),
        ],
    )

    assert assessment.is_duplicate is False
    assert assessment.matched_task is None
    assert assessment.recommendation == "create_new"


def test_semantic_preparation_contains_real_newline():
    prepared = duplicate.prepare_task_for_semantic_comparison(
        title="Create document question answering",
        description="Allow grounded questions.",
    )

    assert prepared.splitlines() == [
        "Create document question answering",
        "Allow grounded questions.",
    ]
    assert "\\n" not in prepared
