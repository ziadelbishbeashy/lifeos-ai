"""Task tag normalization introduced by Step 9."""

from services.task_service import normalize_task_tags


def test_task_tags_are_normalized_and_deduplicated():
    assert normalize_task_tags(
        " Backend, testing ; backend,  release "
    ) == "Backend, testing, release"


def test_empty_task_tags_become_none():
    assert normalize_task_tags(" , ; ") is None
