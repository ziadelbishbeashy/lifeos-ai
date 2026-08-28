"""Step 16 — structured PDF table extraction and table-aware chunking."""

import json

from database import db
from models import Document, DocumentChunk, DocumentTable, Project
from services.document_chunk_service import rebuild_owned_document_chunks
from services.document_table_service import _split_headers, _to_markdown


def _document(user_id: int) -> Document:
    project = Project(
        user_id=user_id,
        title="Table Project",
        status="In Progress",
        priority="High",
    )
    document = Document(
        project=project,
        filename="results.pdf",
        file_path="stored/results.pdf",
        extracted_text="--- Page 1 ---\nQuarterly sales results and commentary.",
    )
    db.session.add_all([project, document])
    db.session.commit()
    return document


def test_table_header_detection_and_markdown_preserve_relationships():
    rows = [
        ["Product", "Q1", "Q2"],
        ["Laptop", "120", "180"],
        ["Phone", "210", "240"],
    ]

    headers, data = _split_headers(rows)
    markdown = _to_markdown(headers, data, title="Quarterly Sales")

    assert headers == ["Product", "Q1", "Q2"]
    assert data[0] == ["Laptop", "120", "180"]
    assert "Table: Quarterly Sales" in markdown
    assert "| Laptop | 120 | 180 |" in markdown
    assert "| Phone | 210 | 240 |" in markdown


def test_rebuild_adds_structured_table_chunk(app, user):
    with app.app_context():
        document = _document(user)
        table = DocumentTable(
            document_id=document.id,
            user_id=user,
            page_number=1,
            table_index=1,
            title="Quarterly Sales",
            headers_json=json.dumps(["Product", "Q1", "Q2"]),
            rows_json=json.dumps([["Laptop", "120", "180"], ["Phone", "210", "240"]]),
            markdown_text=(
                "Table: Quarterly Sales\n"
                "| Product | Q1 | Q2 |\n"
                "| --- | --- | --- |\n"
                "| Laptop | 120 | 180 |\n"
                "| Phone | 210 | 240 |"
            ),
            row_count=2,
            column_count=3,
            source_fingerprint="a" * 64,
        )
        db.session.add(table)
        db.session.commit()

        result = rebuild_owned_document_chunks(
            document_id=document.id,
            user_id=user,
        )

        table_chunks = [chunk for chunk in result.chunks if chunk.content_type == "table"]
        assert len(table_chunks) == 1
        chunk = table_chunks[0]
        assert chunk.table_id == table.id
        assert chunk.page_start == 1
        assert "[STRUCTURED TABLE 1]" in chunk.text
        assert "Laptop | 120 | 180" in chunk.text
        assert "Phone | 210 | 240" in chunk.text

        persisted = DocumentChunk.query.filter_by(table_id=table.id).one()
        assert persisted.content_type == "table"
