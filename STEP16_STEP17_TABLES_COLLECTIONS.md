# LifeOS Document Brain — Steps 16 & 17

## Step 16 — Tables & structured content

LifeOS now detects native/vector tables in readable PDFs with PyMuPDF and preserves the table relationship instead of relying only on flattened PDF text.

Flow:

`PDF -> native text extraction -> table detection -> rows/columns -> structured table chunk -> existing BM25 + embeddings + Hybrid RAG -> existing answerability verifier -> grounded Ask AI`

Important behavior:
- New readable PDF uploads automatically attempt table extraction.
- Old PDFs can be re-scanned from the new **Tables** tab.
- Each table stores page number, table index, optional title, headers, rows, dimensions, Markdown representation, and source fingerprint.
- Table chunks use the existing `DocumentChunk` / Hybrid RAG pipeline. There is no second RAG system.
- Table-aware source metadata includes `content_type=table` and `table_id`.
- Document and project Q&A cache fingerprints now include structured-table state so a newly extracted table cannot leave an old cached answer current.
- This pass targets native/vector PDF tables. Image-only/scanned table quality remains dependent on the OCR work that was intentionally parked.

API:
- `GET /api/v1/documents/<id>/tables`
- `POST /api/v1/documents/<id>/tables/extract` with `{ "force": true }`

## Step 17 — Document Collections

Collections let a user group current PDFs from different projects and ask one grounded question across the group.

Flow:

`selected collection -> current member documents -> existing document chunks/embeddings -> collection-wide keyword + semantic fusion -> existing answerability verifier -> grounded AI answer with document/page evidence`

Important behavior:
- Collections are ownership-scoped.
- A user cannot add another user's document.
- Only the current document version may be added.
- When a new immutable version becomes current, existing collection membership is migrated to the new version automatically.
- Collection Q&A keeps the existing grounding rules and does not answer from outside model knowledge when evidence is insufficient.
- Structured table chunks participate automatically in collection retrieval.
- Collection source cards retain filename, document ID, page, evidence, chunk ID, and table metadata.

API:
- `GET /api/v1/document-collections`
- `POST /api/v1/document-collections`
- `GET/PATCH/DELETE /api/v1/document-collections/<id>`
- `POST /api/v1/document-collections/<id>/documents`
- `DELETE /api/v1/document-collections/<id>/documents/<document_id>`
- `POST /api/v1/document-collections/<id>/questions`
- `GET /api/v1/document-collections/<id>/questions`

Frontend:
- `/documents/collections`
- Document Brain header has a **Collections** entry.
- Document details has a **Tables** tab.
- Collection evidence can open its source document directly at the cited PDF page.

## Database migrations

- `20260828_0001` — structured document tables + table-aware chunks
- `20260828_0002` — document collections + memberships + collection question history

Expected Alembic head: `20260828_0002`
