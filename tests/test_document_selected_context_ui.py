"""Static UI contracts for Step 8D selected PDF context."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pdf_selection_toolbar_and_ask_context_card_exist():
    template = (ROOT / "templates" / "document_details.html").read_text(
        encoding="utf-8"
    )

    assert "data-db-pdf-selection-toolbar" in template
    assert "data-db-pdf-selection-ask" in template
    assert "data-db-pdf-selection-copy" in template
    assert "data-db-selected-context-card" in template
    assert 'name="selected_context_text"' in template
    assert 'name="selected_context_page"' in template
    assert "data-db-remove-selected-context" in template


def test_viewer_keeps_selected_highlight_until_context_is_removed():
    script = (ROOT / "static" / "js" / "document-pdf-viewer.js").read_text(
        encoding="utf-8"
    )

    assert "attachPendingSelectionToAsk" in script
    assert "db-user-context-highlight" in script
    assert "applyAttachedContextHighlightForCurrentPage" in script
    assert "clearAttachedContext" in script
    assert "this.askTab.click()" in script
