# Step 11 description-overlap fix

## Why the test failed

The existing duplicate score blended:
- title: 50%
- description: 20%
- semantic: 30% when available

When semantic matching was intentionally unavailable in the test, a title score
of 0.50 and a description score of 1.00 produced an overall score of 0.6429,
below the 0.72 duplicate threshold.

That meant even a nearly identical description could not trigger a duplicate
unless the title was also very strong.

## Fix

Step 11 now has an additional safe duplicate rule:

- description similarity >= 0.90
- AND title similarity >= 0.35

This allows strongly matching descriptions to confirm related work while
avoiding the unsafe rule "same description alone means duplicate".

The normal overall/title/semantic duplicate rules remain unchanged.

Replace:
- services/task_duplicate_service.py

Add:
- tests/test_task_duplicate_description_regression.py

No database migration is required.
