"""Step 11 unit tests for project duplicate-work intelligence."""

from types import SimpleNamespace

from services import task_duplicate_service as duplicate


def make_task(
    *,
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


def test_exact_active_task_recommends_continue_existing(monkeypatch):
    monkeypatch.setattr(
        duplicate,
        "_semantic_similarity_scores",
        lambda **kwargs: [0.99],
    )

    assessment = duplicate.assess_task_duplicate(
        suggestion_title="Prepare deployment checklist",
        suggestion_description="Prepare production release checklist.",
        existing_tasks=[
            make_task(
                task_id=1,
                title="Prepare deployment checklist",
                description="Create the production release checklist.",
                status="In Progress",
            ),
        ],
    )

    assert assessment.is_duplicate is True
    assert assessment.matched_task.id == 1
    assert assessment.recommendation == "continue_existing"


def test_completed_duplicate_recommends_review_and_update(monkeypatch):
    monkeypatch.setattr(
        duplicate,
        "_semantic_similarity_scores",
        lambda **kwargs: [0.95],
    )

    assessment = duplicate.assess_task_duplicate(
        suggestion_title="Add authentication regression tests",
        suggestion_description="Cover authentication access behavior.",
        existing_tasks=[
            make_task(
                task_id=4,
                title="Add authentication regression tests",
                description="Test authentication routes.",
                status="Completed",
            ),
        ],
    )

    assert assessment.is_duplicate is True
    assert assessment.recommendation == "update_existing"


def test_description_overlap_can_strengthen_duplicate_detection(monkeypatch):
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
                status="Pending",
            ),
        ],
    )

    assert assessment.description_score >= 0.8
    assert assessment.is_duplicate is True


def test_semantic_paraphrase_can_detect_duplicate(monkeypatch):
    monkeypatch.setattr(
        duplicate,
        "_semantic_similarity_scores",
        lambda **kwargs: [0.91],
    )

    assessment = duplicate.assess_task_duplicate(
        suggestion_title="Harden private file access",
        suggestion_description="Prevent one account from reading another user's PDFs.",
        existing_tasks=[
            make_task(
                task_id=10,
                title="Enforce document ownership authorization",
                description="Protect cross-user PDF access.",
                status="Pending",
            ),
        ],
    )

    assert assessment.semantic_score == 0.91
    assert assessment.is_duplicate is True


def test_low_overlap_recommends_create_new(monkeypatch):
    monkeypatch.setattr(
        duplicate,
        "_semantic_similarity_scores",
        lambda **kwargs: [0.2],
    )

    assessment = duplicate.assess_task_duplicate(
        suggestion_title="Prepare presentation slides",
        suggestion_description="Create the final demo deck.",
        existing_tasks=[
            make_task(
                task_id=12,
                title="Optimize SQL indexes",
                description="Improve query performance.",
                status="In Progress",
            ),
        ],
    )

    assert assessment.is_duplicate is False
    assert assessment.recommendation == "create_new"


def test_semantic_failure_falls_back_to_lexical(monkeypatch):
    monkeypatch.setattr(
        duplicate,
        "_semantic_similarity_scores",
        lambda **kwargs: [None],
    )

    assessment = duplicate.assess_task_duplicate(
        suggestion_title="Build login tests",
        suggestion_description=None,
        existing_tasks=[
            make_task(
                task_id=14,
                title="Build login tests",
                status="Pending",
            ),
        ],
    )

    assert assessment.is_duplicate is True
    assert assessment.semantic_score is None
