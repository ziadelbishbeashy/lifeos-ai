# LifeOS Step 13B + 13C — Evidence Builder + Semantic Comparison

This package implements the next two backend stages of Step 13.

## Step 13B — Evidence / candidate builder

New:
- `services/document_comparison_candidate_service.py`

Behavior:
1. Re-validates the ordered owned A/B pair through Step 13A.
2. Finds the newest CURRENT structured analysis for each document.
3. Ignores stale structured analysis as current truth.
4. Converts page-aware structured findings into an A/B evidence registry:
   - key points
   - requirements
   - decisions
   - risks
   - deadlines
   - action items
   - type-specific findings
5. Supplements current structured analysis with a small page-diverse chunk set.
6. If no current analysis exists, falls back to a larger page-diverse chunk set.
7. Assigns stable prompt-local source IDs:
   - A1, A2, ...
   - B1, B2, ...
8. Preserves filename, page, section, evidence, origin and backend chunk provenance.

## Step 13C — Semantic alignment + classification

New:
- `services/document_comparison_alignment_service.py`
- `services/document_comparison_analysis_service.py`
- `services/document_comparison_draft_service.py`

Updated:
- `services/ai_service.py`

### Alignment
LifeOS first creates advisory A/B pair hints using:
- deterministic lexical similarity
- Gemini semantic embeddings when configured

All comparison evidence is embedded in one batch, then A/B similarities are
calculated. Semantic failure never blocks comparison; lexical hints remain.

The alignment context sent to the comparison model contains only source-pair
identities such as:

    A1 ↔ B3

It does NOT expose scores, embedding models, chunk IDs or retrieval ranks.

To disable comparison embeddings:

    DOCUMENT_COMPARISON_SEMANTIC_ALIGNMENT_ENABLED=0

Live semantic alignment is automatically disabled inside Flask TESTING
contexts so pytest does not unexpectedly call Gemini.

### AI classification
The model classifies only material differences:
- `changed`
- `added`
- `removed`
- `potential_conflict`

Important rules:
- A is the baseline.
- B is compared against A.
- Rewording with the same meaning is not a change.
- B is never assumed to be newer/current/authoritative.
- Added/Removed is conservative when evidence is chunk-only or truncated.
- The model may cite only A/B registry IDs.
- Step 13C structurally normalizes output, but does not yet claim each citation
  proves the finding.

## Trust boundary

`document_comparison_draft_service.py` intentionally returns an IN-MEMORY
normalized draft.

It does not save a newly generated comparison as `Completed`.

Step 13D still needs to verify every cited source and enforce:
- changed -> A + B support
- potential conflict -> A + B support
- added -> B support
- removed -> A support

Only after Step 13D should a new comparison be persisted as trusted and
reusable.

If Step 13A finds an already-Completed exact-fingerprint comparison, the draft
service may reuse that existing trusted comparison.

## No database migration

13B/C add no columns or tables.

The latest migration remains:

    20260811_0001

## Apply after Step 13A

Add:
- services/document_comparison_candidate_service.py
- services/document_comparison_alignment_service.py
- services/document_comparison_analysis_service.py
- services/document_comparison_draft_service.py

Replace:
- services/ai_service.py

Add the Step 13B/C tests.

## Test

Focused:

    python -m pytest `
        tests\test_document_comparison_candidates_step13b.py `
        tests\test_document_comparison_analysis_step13c.py `
        tests\test_document_comparison_alignment_step13c.py `
        tests\test_ai_service_document_comparison_step13c.py `
        tests\test_document_comparison_draft_step13bc.py `
        -v

Then:

    python -m pytest

## Next

Step 13D will validate every A/B citation against the exact candidate registry,
enforce category-specific evidence requirements, and persist only verified
comparison results.
