# LifeOS Step 13A — Document Comparison Foundation

Step 13A is the non-AI foundation for Step 13 "Compare Two Documents".

## Included

### 13A.1 Model
`DocumentComparison` stores:
- user ownership
- ordered Document A / Document B references
- summary
- future findings JSON
- provider/model
- Pending / Completed / Failed status
- ordered source fingerprint
- error message and created time

A database check prevents A == B.

### 13A.2 SQL Server-safe migration
Revision:
- `20260811_0001`
- down revision `20260810_0002`

Important SQL Server decision:
- user FK: `ON DELETE CASCADE`
- document A FK: `ON DELETE NO ACTION`
- document B FK: `ON DELETE NO ACTION`

Both document relationships are deliberately symmetric. This avoids SQL Server
error 1785 (multiple cascade paths).

### 13A.3 Ownership + pair validation
`services/document_comparison_service.py`:
- validates IDs
- rejects the same document twice
- independently verifies ownership of A and B through the existing Document
  access boundary
- uses neutral not-found behavior for another user's document
- preserves A -> B order

### 13A.4 Ordered fingerprint + caching
The fingerprint includes:
- comparison schema version
- Document A ID, filename and extracted-text SHA-256
- Document B ID, filename and extracted-text SHA-256

Therefore:
- same A -> B + same content => same fingerprint
- B -> A => different fingerprint
- changed A or B => different fingerprint

Only an exact `Completed` comparison for:
- same user
- same A
- same B
- same fingerprint

is reusable. `force=True` bypasses reuse.

### 13A.5 Foundation tests
Coverage includes:
- model JSON safety
- database A != B constraint
- same-document rejection
- foreign-document ownership isolation
- invalid IDs
- directional fingerprints
- source-change invalidation
- exact completed-cache reuse
- failed/stale cache rejection
- force bypass
- owner-scoped history
- SQL Server migration contract
- safe project deletion with comparison cleanup

## Project deletion safeguard

Because the two document foreign keys use `NO ACTION`, deleting a project could
otherwise fail when one of its documents participates in a saved comparison.

`project_service.delete_project()` now removes comparison rows referencing the
project's documents in the same transaction before the project/document delete
cascade proceeds.

This prevents Step 13A from introducing a regression into existing project
deletion.

## Apply

Replace:
- `models.py`
- `services/project_service.py`

Add:
- `services/document_comparison_service.py`
- `migrations/versions/20260811_0001_add_document_comparisons.py`
- `sql/step13a_document_comparisons.sql`
- Step 13A tests

## Migration

The user's previous failed migration remained at `20260810_0002`, so no rollback
or new revision is required. Replace the failed migration file with the corrected
one, then run:

    python -m flask --app app db upgrade
    python -m flask --app app db current

Expected head:

    20260811_0001

Do not run the manual SQL file after Alembic succeeds.

## Scope boundary

Step 13A intentionally does NOT:
- compare meanings
- create AI prompts
- align semantic topics
- classify Changed / Added / Removed / Potential Conflict
- verify comparison evidence
- add comparison UI

Those belong to 13B-13F.
