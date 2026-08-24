"""Step 13E/F reader-facing comparison UI contract tests."""

from pathlib import Path

from jinja2 import Environment


ROOT = Path(
    __file__
).resolve().parents[1]


def test_compare_page_exposes_ordered_a_b_workflow():
    template = (
        ROOT
        / "templates"
        / "document_compare.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Baseline document" in template
    assert "Compare against" in template
    assert "Compare documents" in template
    assert "data-comparison-swap" in template
    assert "Recent comparisons" in template


def test_result_page_has_category_sections_and_pdf_source_links():
    template = (
        ROOT
        / "templates"
        / "document_comparison_details.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Changed" in template
    assert "Added in B" in template
    assert "Removed from B" in template
    assert "Potential conflicts" in template
    assert "View A source" in template
    assert "View B source" in template
    assert "pdf_page=source.page" in template


def test_result_ui_does_not_expose_backend_similarity_or_chunk_metadata():
    template = (
        ROOT
        / "templates"
        / "document_comparison_details.html"
    ).read_text(
        encoding="utf-8"
    )

    forbidden = (
        "chunk_id",
        "chunk_index",
        "semantic_score",
        "similarity_score",
        "keyword_rank",
        "embedding_model",
    )

    for value in forbidden:
        assert value not in template


def test_step13_templates_parse():
    environment = Environment()

    for name in (
        "document_compare.html",
        "document_comparison_details.html",
        "documents.html",
    ):
        environment.parse(
            (
                ROOT
                / "templates"
                / name
            ).read_text(
                encoding="utf-8"
            )
        )
