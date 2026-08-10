# LifeOS Document Brain — Step 8A Navigation Backend

This patch implements the backend foundation for Step 8.

Locked design decisions:
- Open Page will use an in-LifeOS PDF modal with an option to open a new tab.
- View Context will use a right-side drawer.
- Context includes previous + current + next chunks even across page boundaries.
- Page changes remain explicit because every chunk keeps its own page label.
- Ask About This will later carry the selected trusted chunk into Ask Document.
- Copy will later support excerpt-only and excerpt-with-citation.
- Source actions will appear in Search and Ask Document.
- PDF.js will be integrated in Step 8B.
- Ask Document source identity uses option B: save database chunk_id + chunk_index
  inside sources_json. No migration is required.

New backend routes:
GET /documents/<document_id>/file
GET /documents/<document_id>/context/<chunk_id>

Security rules:
- Document ownership is resolved through Project.user_id.
- A chunk must belong to the requested document and current user.
- The browser never submits or receives the raw storage path.
- The original PDF is served through an authenticated route.
- Private PDF responses use no-store caching.
- Existing saved answers without chunk_id remain readable; later UI will allow
  Open Page from their page number but disable chunk-dependent actions until
  the answer is regenerated.

Source JSON for new Ask Document answers now includes:
{
  "source_id": 1,
  "chunk_id": 57,
  "chunk_index": 12,
  "page": 8,
  "section": "Privacy",
  "evidence": "...",
  "preview_type": "focused"
}

No database migration is required.
