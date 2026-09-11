"""Step 12 project multi-document RAG UI contract tests."""

from pathlib import Path
from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]


def test_project_page_contains_multi_document_question_workspace():
    template = (ROOT / "templates" / "project_details.html").read_text(encoding="utf-8")

    assert 'data-project-studio-tab="ask-project"' in template
    assert 'data-project-studio-panel="ask-project"' in template
    assert "Ask across linked PDFs" in template
    assert "project_bp.ask_project_documents_route" in template
    assert "Supporting sources" in template
    assert "filename" in template
    assert "pdf_page" in template

    # Reader-facing UI must not expose backend retrieval internals.
    assert "semantic_score" not in template
    assert "keyword_rank" not in template
    assert "chunk_index" not in template


def test_project_template_parses_after_step12():
    Environment().parse(
        (ROOT / "templates" / "project_details.html").read_text(encoding="utf-8")
    )
