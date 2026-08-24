"""Step 11 reader-facing duplicate-review UI contract tests."""

from pathlib import Path

from jinja2 import Environment


ROOT = Path(__file__).resolve().parents[1]


def test_duplicate_review_shows_recommendation_without_raw_scores():
    template = (
        ROOT
        / "templates"
        / "_document_task_suggestions.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "LifeOS recommends" in template
    assert "Continue existing task" in template
    assert "Review and update existing task" in template
    assert "View existing" in template
    assert "Create anyway" in template
    assert "Ignore" in template

    # Similarity internals stay backend-only.
    assert "{{ suggestion.match_score }}" not in template
    assert "semantic_score" not in template
    assert "title_score" not in template


def test_duplicate_template_still_parses():
    template = (
        ROOT
        / "templates"
        / "_document_task_suggestions.html"
    ).read_text(
        encoding="utf-8"
    )

    Environment().parse(template)
