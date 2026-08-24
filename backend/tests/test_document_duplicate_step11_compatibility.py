"""Step 11 compatibility tests for Document Brain task conversion."""

from types import SimpleNamespace

from services import document_task_suggestion_service as suggestions


def test_step9_title_similarity_api_remains_available():
    score = suggestions.calculate_task_match_score(
        "Build authentication tests",
        "Build authentication tests",
    )

    assert score == 1.0


def test_step9_find_best_match_api_remains_available(monkeypatch):
    monkeypatch.setenv(
        "TASK_DUPLICATE_SEMANTIC_ENABLED",
        "0",
    )

    tasks = [
        SimpleNamespace(
            id=1,
            title="Prepare deployment checklist",
            description=None,
            status="Pending",
        ),
        SimpleNamespace(
            id=2,
            title="Optimize database indexes",
            description=None,
            status="Pending",
        ),
    ]

    matched, score = suggestions.find_best_task_match(
        suggestion_title="Prepare deployment checklist",
        existing_tasks=tasks,
    )

    assert matched.id == 1
    assert score == 1.0
