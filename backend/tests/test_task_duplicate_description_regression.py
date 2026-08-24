"""Regression tests for Step 11 description-supported duplicate detection."""

from types import SimpleNamespace

from services import task_duplicate_service as duplicate


def make_task(
    *,
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


def test_strong_description_plus_related_title_is_duplicate(monkeypatch):
    monkeypatch.setattr(
        duplicate,
        "_semantic_similarity_scores",
        lambda **kwargs: [None],
    )

    assessment = duplicate.assess_task_duplicate(
        suggestion_title="Release verification",
        suggestion_description=(
            "Run the final production security checklist and verify "
            "document ownership routes."
        ),
        existing_tasks=[
            make_task(
                task_id=8,
                title="Final release checks",
                description=(
                    "Verify document ownership routes and run the final "
                    "production security checklist."
                ),
            ),
        ],
    )

    assert assessment.title_score >= 0.35
    assert assessment.description_score >= 0.90
    assert assessment.is_duplicate is True


def test_identical_description_with_unrelated_title_is_not_enough(monkeypatch):
    monkeypatch.setattr(
        duplicate,
        "_semantic_similarity_scores",
        lambda **kwargs: [None],
    )

    assessment = duplicate.assess_task_duplicate(
        suggestion_title="Prepare presentation slides",
        suggestion_description="Use the standard project checklist.",
        existing_tasks=[
            make_task(
                task_id=9,
                title="Optimize SQL indexes",
                description="Use the standard project checklist.",
            ),
        ],
    )

    assert assessment.description_score == 1.0
    assert assessment.title_score < 0.35
    assert assessment.is_duplicate is False
