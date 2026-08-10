# Step 11 backward-compatibility fix

## Root cause

Step 11 moved duplicate thresholds into `task_duplicate_service.py`, but the
existing Step 9 test suite still imports:

    MATCH_THRESHOLD

from `document_task_suggestion_service.py`.

The Step 11 refactor also accidentally removed `_normalise_match_text()` even
though `build_document_task_suggestions()` still uses it to prevent duplicate
suggestions from the same analysis.

## Fix

- Restored `MATCH_THRESHOLD` as a compatibility alias to
  `DUPLICATE_OVERALL_THRESHOLD`.
- Restored `_normalise_match_text()`.
- Added regression tests for both contracts.

Replace:
- services/document_task_suggestion_service.py

Add:
- tests/test_step11_backward_compatibility_regression.py

No database migration is required.
