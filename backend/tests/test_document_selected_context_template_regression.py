"""Regression tests for selected-context history rendering."""

from pathlib import Path

from jinja2 import Environment


ROOT = Path(__file__).resolve().parents[1]


def test_question_history_does_not_reference_undefined_selected_context():
    template_text = (
        ROOT
        / "templates"
        / "document_details.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "{% elif not selected_context.value %}" not in template_text
    assert "namespace(cited=0, selected=0)" in template_text
    assert "{% elif not source_counts.selected %}" in template_text


def test_document_details_template_still_parses():
    template_text = (
        ROOT
        / "templates"
        / "document_details.html"
    ).read_text(
        encoding="utf-8"
    )

    Environment().parse(
        template_text
    )
