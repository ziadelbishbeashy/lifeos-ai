# Step 20 — Limits & Cost Controls

Step 20 does **not** create another AI/RAG system. It puts reviewed boundaries
around the existing Document Brain pipeline so one request cannot unexpectedly
consume unbounded storage, OCR, embeddings, retrieval context, or provider work.

## Default policy

- PDF upload size: **25 MB**
- PDF pages: **300**
- extracted text retained per PDF: **200,000 characters**
- searchable chunks per document: **250**
- documents searched in one Project / Collection / Module scope: **50**
- retrieval results: **12 maximum**
- RAG context sent to AI: **20,000 characters maximum**
- provider prompt: **120,000 characters maximum**
- text-generation calls in one HTTP request: **4 maximum**
- embedding batch: **50 chunks maximum**
- embedding provider calls in one HTTP request: **12 maximum**
- embedding input in one HTTP request: **120,000 characters maximum**

Every value is environment-configurable. The defaults are intentionally large
enough for current LifeOS workflows while preventing accidental runaway work.

## Cost behaviour

LifeOS continues to reuse existing chunk embeddings. Step 20 counts only actual
embedding provider calls, so reused embeddings do not consume the request budget.
If a workspace needs more semantic indexing than one request allows, the existing
keyword/BM25 fallback remains available and later requests can continue embedding
from the persisted state.

Generation-call limits are enforced at the provider router. A Step 20 budget
rejection never triggers a fallback provider, because that would spend another
external call after LifeOS intentionally stopped the request.

The backend logs provider *metadata only* (`operation`, provider, model, input
characters, call index). API keys, prompts, and document text are not logged by
the Step 20 usage logger.

## Inspect active limits

```powershell
python -m flask --app app resource-limits
```

This is the quickest deployment check after changing `.env` values.

## Product behaviour

- Oversized page-count PDFs are rejected and cleaned up instead of being kept as
  broken/OCR-pending uploads.
- Existing documents that exceed a newly lowered chunk limit fail with a clear
  resource-limit message rather than silently sending huge contexts.
- Project, Collection, Module, and Lecture retrieval remain ownership-safe and
  grounded; Step 20 only bounds the size of the authorized scope.
- No new database migration is required for Step 20.
