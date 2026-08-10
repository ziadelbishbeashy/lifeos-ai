# Step 11 semantic false-positive fix

## Root cause

The old Step 9 test expected:

- "Build secure PDF upload" -> matches the existing PDF-upload task
- "Create document question answering" -> does NOT match that task

Step 11 introduced live semantic embeddings. Because the local environment has
Gemini embedding configuration, the old test now executes semantic comparison.
The semantic-only duplicate threshold was 0.82, which is too permissive for
task embeddings and allowed the unrelated question-answering action to match
the PDF-upload task.

There was also a second problem: every task embedding contained the same long
instruction prefix. Shared boilerplate can artificially increase cosine
similarity between otherwise different tasks.

## Fix

1. Semantic-only duplicate threshold:
   - old: 0.82
   - new: 0.90

2. Task embedding text now contains only:
   - task title
   - task description

   The common instruction prefix was removed.

3. Lexical title/description and the strong-description rule remain unchanged.

This keeps paraphrase detection while reducing false positives.

Replace:
- services/task_duplicate_service.py

Add:
- tests/test_step11_semantic_false_positive_regression.py

No migration is required.
