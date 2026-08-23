# LifeOS Step 13 — Compare Two Documents (Complete)

This is the consolidated Step 13 package. It contains 13A through 13F.

## 13A — Comparison foundation
- `DocumentComparison` model
- SQL Server-safe migration `20260811_0001`
- A != B database constraint
- ordered A -> B ownership validation
- directional SHA-256 fingerprint
- exact Completed-result reuse
- owner-scoped comparison history
- project-delete cleanup for SQL Server `NO ACTION` document foreign keys

## 13B — Evidence / candidate builder
- current structured analysis is preferred
- stale structured analysis is excluded as current truth
- page-aware chunk fallback
- document-wide chunk coverage
- prompt-local source registry `A1...` and `B1...`
- page/section/evidence + backend provenance retained

## 13C — Semantic alignment + classification
- lexical A/B alignment hints
- Gemini embedding alignment when configured
- one embedding batch for comparison evidence
- provider failure falls back to lexical hints
- testing mode does not make live Gemini embedding calls
- AI draft categories:
  - changed
  - added
  - removed
  - potential_conflict
- rewording is not a change
- B is never assumed to be newer/current/authoritative
- newly generated drafts are NOT persisted yet

## 13D — Evidence verification + trusted persistence
New:
- `services/document_comparison_verifier_service.py`
- `services/document_comparison_workflow_service.py`

The final workflow is:

    A/B ownership + fingerprint
            ↓
    evidence registry
            ↓
    semantic comparison draft
            ↓
    deterministic source validation
            ↓
    second evidence verifier
            ↓
    trusted source snapshots
            ↓
    status = Completed

Fail-closed rules:
- Changed -> valid A + B evidence
- Potential conflict -> valid A + B evidence
- Added -> valid B evidence AND current/non-truncated structured coverage for A
- Removed -> valid A evidence AND current/non-truncated structured coverage for B
- unknown source IDs -> rejected
- medium/low verifier confidence -> rejected
- if generated findings exist but none verify -> comparison fails
- failed verification is saved as `Failed`, never reused

The saved summary is rebuilt by LifeOS from verified finding counts rather than
trusting an unrestricted AI summary.

## 13E — Comparison UI + PDF navigation
Routes:
- `GET/POST /documents/compare`
- `GET /documents/comparisons/<id>`
- `POST /documents/comparisons/<id>/rerun`

UI:
- Document A baseline selector
- Document B selector
- swap control
- same-document client + backend protection
- comparison history
- verified category counts
- Changed / Added / Removed / Potential Conflict sections
- exact source filename/page/evidence
- View A source / View B source navigation back to the full PDF workspace
- refresh comparison
- failed comparison state
- no-material-difference state

The UI deliberately hides:
- chunk IDs
- chunk indexes
- similarity scores
- retrieval ranks
- embedding/provider internals

## 13F — Reliability + integration tests
Coverage includes:
- SQL Server migration behavior
- model safety
- ownership isolation
- A/B direction
- fingerprint invalidation
- cache reuse
- stale-analysis fallback
- semantic alignment
- unknown source rejection
- category-specific source requirements
- conservative Added/Removed absence claims
- high-confidence verification requirement
- failed comparison persistence
- route ownership
- PDF source links
- template parsing
- developer metadata hidden from the user
- project deletion regression

## Database

Step 13 uses one migration only:

    20260811_0001

If Step 13A migration already succeeded, do NOT generate or run another
migration for B-F.

If your database is still at `20260810_0002`, apply:

    python -m flask --app app db upgrade

Expected:

    20260811_0001

## Apply

This ZIP is consolidated. Extract it over the current LifeOS project and replace
matching files.

Do not apply older Step 13A or Step 13B/C packages after this package.

## Focused tests

    python -m pytest `
        tests\test_document_comparison_model_step13a.py `
        tests\test_document_comparison_service_step13a.py `
        tests\test_document_comparison_project_delete_step13a.py `
        tests\test_document_comparison_migration_step13a.py `
        tests\test_document_comparison_candidates_step13b.py `
        tests\test_document_comparison_analysis_step13c.py `
        tests\test_document_comparison_alignment_step13c.py `
        tests\test_ai_service_document_comparison_step13c.py `
        tests\test_document_comparison_draft_step13bc.py `
        tests\test_document_comparison_verifier_step13d.py `
        tests\test_document_comparison_workflow_step13d.py `
        tests\test_document_comparison_routes_step13e.py `
        tests\test_document_comparison_ui_step13e.py `
        tests\test_document_comparison_trust_step13f.py `
        -v

Then:

    python -m pytest

## Manual browser acceptance test

1. Upload/analyse two PDFs with overlapping requirements.
2. Open Document Brain -> Compare documents.
3. Select A and B and compare.
4. Confirm reworded equivalent content is not reported as a change.
5. Confirm a changed value appears under Changed with A/B evidence.
6. Confirm source buttons open the correct PDF/page.
7. Reverse A/B and confirm direction is preserved.
8. Refresh comparison.
9. Ask for the same unchanged pair again and confirm the cached result is reused.
10. Modify/re-upload source content later; the ordered content fingerprint must
    prevent stale reuse.

## Step 13 scope boundary

Step 13 does NOT:
- declare which selected file is the latest version
- automatically supersede old information
- maintain page-level version history
- OCR image-only PDFs
- compare tables structurally
- compare more than two documents at once

Those remain later roadmap capabilities, beginning with Step 14 versioning.
