"""Step 14 reader-facing version UI and trust-boundary tests."""

from pathlib import Path

from jinja2 import Environment


ROOT = Path(__file__).resolve().parents[1]


def test_document_details_has_current_previous_timeline_and_upload():
    template = (
        ROOT / "templates" / "document_details.html"
    ).read_text(encoding="utf-8")

    assert "Document versioning" in template
    assert "Upload new version" in template
    assert "Compare with current" in template
    assert "Historical information" in template
    assert "Open current version" in template


def test_historical_answers_are_visible_but_labeled():
    template = (
        ROOT / "templates" / "document_details.html"
    ).read_text(encoding="utf-8")

    assert '"Historical", "Outdated"' in template
    assert "Historical answer" in template
    assert "not current project truth" in template


def test_project_page_labels_outdated_project_rag_answers():
    template = (
        ROOT / "templates" / "project_details.html"
    ).read_text(encoding="utf-8")

    assert "Outdated answer" in template
    assert "newer version" in template


def test_version_templates_parse():
    environment = Environment()

    for name in (
        "document_details.html",
        "documents.html",
        "project_details.html",
    ):
        environment.parse(
            (ROOT / "templates" / name).read_text(encoding="utf-8")
        )


def test_project_current_intelligence_services_use_version_filter():
    for relative in (
        "services/project_document_retrieval_service.py",
        "services/project_question_workflow_service.py",
        "services/workspace_context_service.py",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "current_document_filter" in text
