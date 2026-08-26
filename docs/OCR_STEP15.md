# Step 15 — OCR for scanned and mixed PDFs

## Goal

Document Brain already extracts embedded PDF text with `pypdf`. Step 15 adds an
OCR fallback only for pages whose embedded text is missing or too weak. OCR then
feeds the same page markers, chunks, embeddings and hybrid RAG used by normal
PDFs. There is no second OCR-specific RAG pipeline.

## Processing path

```text
PDF
  -> inspect each page with pypdf
  -> native text page: keep native text
  -> scanned/weak page: render only that page -> OCR
  -> rebuild page-marked extracted_text
  -> existing document_chunk_service
  -> existing embeddings/hybrid retrieval on demand
```

The OCR pass preserves `--- Page N ---` markers, so Verify/evidence can still
resolve to the original PDF page.

## Persisted OCR state

Each `Document` now stores:

- `ocr_status`: `not_needed`, `pending`, `queued`, `processing`, `completed`, `failed`
- `ocr_provider` (backend-only)
- `ocr_started_at`, `ocr_completed_at`
- `ocr_total_pages`
- `ocr_pages_requested`
- `ocr_pages_processed`
- `ocr_low_confidence_pages`
- `ocr_average_confidence`
- `ocr_error`

The React API exposes product-level status/progress/confidence but deliberately
does not expose the OCR provider.

## Provider boundary

The first provider is local Tesseract. The workflow depends only on
`OCRProvider`, so a managed provider can replace or supplement Tesseract later.

Python dependencies are installed from `backend/requirements.txt`, but the
Tesseract executable itself must also be installed on the host.

Example `backend/.env` on Windows:

```env
OCR_PROVIDER=tesseract
OCR_LANGUAGES=eng
OCR_TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
OCR_RENDER_DPI=300
OCR_LOW_CONFIDENCE_THRESHOLD=0.70
OCR_AUTO_ENQUEUE=false
```

For English + Arabic, install the Arabic Tesseract language pack and use:

```env
OCR_LANGUAGES=eng+ara
```

`OCR_AUTO_ENQUEUE` stays false until the deployment uses a durable background
queue. With the current development `inline` backend, OCR can execute in the web
request and therefore is better triggered explicitly during local development.

## API

Read status:

```http
GET /api/v1/documents/{document_id}/ocr
```

Start or retry OCR:

```http
POST /api/v1/documents/{document_id}/ocr
Content-Type: application/json

{}
```

Force a rerun after a completed/not-needed state:

```json
{"force": true}
```

The endpoint is ownership-safe and queues the existing `document.ocr` job.

## Failure behavior

A provider/render failure sets `ocr_status=failed` and stores a user-safe error.
The PDF and any previously extracted native text remain intact. A retry can be
queued later. If OCR succeeds but chunk rebuilding fails, OCR remains completed;
indexing can be retried independently.

## Migration

Run:

```powershell
cd backend
python -m flask --app app db upgrade
```

Expected new Alembic head:

```text
20260826_0001
```

## Tests

The Step 15 tests cover:

- mixed PDFs OCR only missing pages
- native text preservation
- low-confidence accounting
- OCR success -> existing chunk pipeline
- provider failure -> retryable failed state without losing text
- queue idempotency
- JSON API status/start and cross-user ownership protection
- migration chain

The complete backend regression remains the release gate.
