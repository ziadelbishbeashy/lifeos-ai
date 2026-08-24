"""Static contract tests for Step 8C reader-first PDF UX."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pdf_workspace_does_not_render_developer_search_details():
    template = (
        ROOT / "templates/document_details.html"
    ).read_text(encoding="utf-8")

    assert "Read and explore the original PDF" in template
    assert "data-db-pdf-semantic-search-url" in template
    assert "Search by meaning" in template
    assert "data-db-pdf-text-layer" in template

    assert "Semantic similarity" not in template
    assert "Keyword rank" not in template
    assert "Semantic rank" not in template
    assert "<span>Chunk</span>" not in template


def test_pdf_viewer_contains_semantic_highlight_mapping():
    script = (
        ROOT / "static/js/document-pdf-viewer.js"
    ).read_text(encoding="utf-8")

    assert "searchSemantically" in script
    assert "applySemanticHighlightsForCurrentPage" in script
    assert "new this.pdfjs.TextLayer" in script
    assert "db-semantic-highlight-strong" in script
    assert "db-semantic-highlight-related" in script
    assert "semantic_score" not in script
