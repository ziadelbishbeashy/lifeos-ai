# LifeOS Document Brain — Step 12: Project-wide Multi-document RAG

Step 12 completes Phase 3 of the Document Brain roadmap.

## What it adds

- One project question can retrieve evidence across every readable PDF linked to
  the owned project.
- Retrieval reuses the existing chunking, BM25, embedding and weighted-RRF
  components instead of building a second search stack.
- Keyword ranking is calculated over the combined project chunk corpus.
- Document embeddings are ensured per owned PDF, then the question embedding is
  generated once and ranked globally across the project corpus.
- If semantic retrieval is unavailable, the complete project corpus still uses
  deterministic keyword fallback.
- The answerability verifier filters candidate sources before answer generation.
- The answer model receives only verifier-approved numbered sources.
- Saved sources preserve project_id, document_id, filename, page, section,
  chunk_id/chunk_index and owner-only visibility metadata. Chunk internals remain
  backend-only in the UI.
- Project answers are cached only while the complete readable linked-PDF set is
  unchanged. Changing any linked PDF invalidates reuse through the project source
  fingerprint.
- The Project Studio gets an "Ask Documents" tab with grounded history and
  source links back to the exact PDF page.

## Database change

A new `project_questions` table stores project-wide grounded question history.

Preferred setup:

    python -m flask --app app db upgrade

The included `sql/step12_project_questions.sql` is an alternative for a manual
SQL Server update only. Do not run both.

## Replace

- models.py
- services/ai_service.py
- services/project_service.py
- routes/project_routes.py
- templates/project_details.html
- static/css/theme-v2.css
- static/js/document-pdf-viewer.js

## Add

- services/project_document_retrieval_service.py
- services/project_question_workflow_service.py
- migrations/versions/20260810_0002_add_project_questions.py
- sql/step12_project_questions.sql
- Step 12 tests under tests/

## Validation commands

    python -m py_compile models.py services\ai_service.py services\project_service.py routes\project_routes.py services\project_document_retrieval_service.py services\project_question_workflow_service.py
    node --check static\js\document-pdf-viewer.js
    python -m pytest tests\test_project_document_retrieval_step12.py tests\test_project_question_model_step12.py tests\test_project_question_workflow_step12.py tests\test_ai_service_project_question_step12.py tests\test_project_question_routes_step12.py tests\test_project_question_ui_step12.py tests\test_project_question_migration_step12.py -v
    python -m pytest

## Phase 3 status

- Step 9 — Convert findings into tasks with confirmation ✅
- Step 10 — Connect documents to project context ✅
- Step 11 — Detect duplicate work ✅
- Step 12 — Project-wide multi-document RAG ✅ after local regression passes

## Final retrieval guarantees

- All readable PDFs linked to the owned project are searched as one global retrieval corpus instead of running unrelated per-file answers.
- BM25 candidates are ranked across all project chunks.
- The project question embedding is generated once, then compared with embedded chunks from all searchable project documents.
- Hybrid fusion is applied globally before answerability verification.
- The answer model receives only verifier-approved sources.
- Every saved source keeps project, document, filename, page, section, chunk, ownership/visibility provenance.
- User-facing project Q&A shows filenames/pages/evidence, not chunk IDs, retrieval ranks, or similarity scores.

