# LifeOS Step 14 — Document Versioning

Step 14 turns separate replacement PDFs into one explicit, immutable document history.
It is designed around one rule:

> Preserve historical information, but never present it as current project truth.

## What Step 14 adds

### 14A — Version data model

New model:

- `DocumentVersionFamily`

New `Document` fields:

- `version_family_id`
- `version_number`
- `is_current_version`
- `version_change_json`
- `superseded_at`

Standalone pre-Step-14 documents remain valid and are treated as current documents until a replacement is explicitly uploaded.

Migration:

- revision: `20260811_0002`
- down revision: `20260811_0001`

SQL Server relationships use `ON DELETE NO ACTION` to avoid cascade-path problems.

### 14B — Explicit new-version workflow

On the current Document Brain details page the user can choose **Upload new version**.

The replacement is explicit and user-confirmed. LifeOS does not infer version relationships from filenames.

The old PDF is preserved. The new PDF becomes a separate `Document` row inside the same version family.

Example:

    Requirements
    ├── Version 1 — Previous
    ├── Version 2 — Previous
    └── Version 3 — Current

Uploading from a historical version ID still appends after the family's actual current version.

An exact duplicate file with identical extracted text is rejected to avoid meaningless version history.

### 14C — Change detection

`services/document_version_service.py` records:

- whole extracted-text SHA-256 fingerprints
- whole stored-PDF SHA-256 fingerprints when storage is readable
- changed page numbers
- added page numbers
- removed page numbers
- unchanged page numbers

The page detector uses the existing `--- Page N ---` extraction boundaries.

Each version keeps its own immutable chunks. The existing upload workflow builds the new version's chunks. Step 14 then attempts semantic embedding preparation for the new current version. If embeddings are unavailable, the version remains valid and project retrieval can fall back to keyword search / lazy embedding generation.

This deliberately favors correctness over copying embeddings between versions, because current chunk embedding fingerprints include the source fingerprint of the document/chunk preparation pipeline.

### 14D — Stale-result invalidation

When a current version is superseded, LifeOS marks derived current-state information as historical/outdated:

- `DocumentAIAnalysis`: `Completed -> Outdated`
- `DocumentQuestion`: `Completed -> Outdated`
- pending `DocumentTaskSuggestion`: `Pending -> Outdated`
- `ProjectQuestion`: `Completed -> Outdated`

Created/linked/rejected task suggestions are preserved as already-handled history.

A user may still ask a previous PDF directly. New answers generated intentionally from a previous version are saved as:

- `Historical`

This keeps historical research possible without making it look like current project truth.

New full analysis is blocked on previous versions. The saved previous analysis remains visible for history.

### 14E — Version-aware project intelligence

The following now use only standalone/current version records by default:

- Step 12 project-wide RAG retrieval
- Step 12 project-Q&A source fingerprints / cache identity
- Step 10 shared workspace project document context
- downstream project-aware AI features that consume the shared workspace context

So a project with:

    Requirements v1 — Previous — deadline Aug 20
    Requirements v2 — Current  — deadline Aug 27

will not mix both deadlines into current project RAG.

Previous versions remain individually openable, searchable and comparable.

### 14F — Version-history UI

Document details now show:

- Current / Previous badge
- version number
- upload-new-version workflow on current version
- version timeline
- upload timestamps
- page-change counts
- Open previous/current version
- Compare previous version with current using Step 13
- historical-information warning

Document library cards also label versioned PDFs as Current or Previous.

Old Document Q&A and Project Q&A remain visible with clear historical/outdated warnings.

### 14G — Reliability coverage

Step 14 tests cover:

- version family model/history
- standalone-document compatibility
- page changed/added/removed detection
- current-version activation
- stale analysis/question/task/project-Q&A invalidation
- project source fingerprint ignoring previous versions
- workspace context excluding previous versions
- SQL Server migration contract
- version-history routes/UI
- historical type-analysis protection
- historical Q&A status contract
- project deletion with version-family `NO ACTION` FKs

## Apply

Extract this ZIP over the current LifeOS project after Step 13.

Apply migration:

    python -m flask --app app db current
    python -m flask --app app db upgrade
    python -m flask --app app db current

Expected latest revision:

    20260811_0002

Do **not** run `sql/step14_document_versioning.sql` after Alembic succeeds. That SQL file is only a manual fallback.

## Focused Step 14 tests

    python -m pytest `
        tests\test_document_version_model_step14.py `
        tests\test_document_version_service_step14.py `
        tests\test_document_version_current_rag_step14.py `
        tests\test_document_version_migration_step14.py `
        tests\test_document_version_routes_step14.py `
        tests\test_document_version_ui_step14.py `
        tests\test_document_version_question_status_step14.py `
        tests\test_project_delete_version_family_step14.py `
        -v

Then run the full regression suite:

    python -m pytest

## Manual browser acceptance test

1. Open a current PDF that already has an analysis and saved Q&A.
2. Upload a replacement through **Upload new version**.
3. Confirm the old PDF becomes **Previous** and the new PDF becomes **Current**.
4. Confirm old analysis and old Q&A are labeled outdated/historical.
5. Confirm the new PDF has fresh chunks and can be searched.
6. Confirm Project Ask Documents uses the new current PDF and not the previous version.
7. Open the previous version and ask it a question; the new answer should be labeled **Historical**.
8. Confirm a previous version cannot run a new current analysis.
9. Use **Compare with current** and verify Step 13 opens A=previous, B=current.
10. Upload an identical current PDF and confirm LifeOS rejects it as an identical version.
11. Delete a test project containing versioned documents and confirm project deletion still succeeds.

## Scope boundary

Step 14 does not automatically infer that two arbitrary existing documents are versions of each other. Version history is created through the explicit **Upload new version** action. This prevents accidental stale/current decisions based only on filenames or semantic similarity.

Step 15 remains OCR support for image-only/scanned PDFs.
