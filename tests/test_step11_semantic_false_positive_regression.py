"""Regression guards for Step 11 semantic false-positive control."""

from types import SimpleNamespace

from services import task_duplicate_service as duplicate


def _task(
    task_id: int,
    title: str,
    description: str,
    status: str = "Pending",
):
    return SimpleNamespace(
        id=task_id,
        title=title,
        description=description,
        status=status,
    )


def test_moderately_high_semantic_score_does_not_override_unrelated_work(
    monkeypatch,
):
    monkeypatch.setattr(
        duplicate,
        "_semantic_similarity_scores",
        lambda **kwargs: [0.85],
    )

    assessment = duplicate.assess_task_duplicate(
        suggestion_title="Create document question answering",
        suggestion_description="Allow grounded questions.",
        existing_tasks=[
            _task(
                1,
                "Implement secure PDF upload",
                "Validate and store PDF files.",
            ),
        ],
    )

    assert assessment.semantic_score == 0.85
    assert assessment.title_score < 0.40
    assert assessment.description_score < 0.40
    assert assessment.is_duplicate is False


def test_strong_semantic_paraphrase_still_detects_duplicate(
    monkeypatch,
):
    monkeypatch.setattr(
        duplicate,
        "_semantic_similarity_scores",
        lambda **kwargs: [0.91],
    )

    assessment = duplicate.assess_task_duplicate(
        suggestion_title="Harden private file access",
        suggestion_description=(
            "Prevent one account from reading another user's PDFs."
        ),
        existing_tasks=[
            _task(
                2,
                "Enforce document ownership authorization",
                "Protect cross-user PDF access.",
            ),
        ],
    )

    assert assessment.semantic_score == 0.91
    assert assessment.is_duplicate is True


def test_embedding_text_does_not_include_shared_instruction_prefix():
    prepared = duplicate.prepare_task_for_semantic_comparison(
        title="Create document question answering",
        description="Allow grounded questions.",
    )

    assert prepared == (
        "Create document question answering\n"
        "Allow grounded questions."
    )
    assert "Represent the meaning" not in prepared
