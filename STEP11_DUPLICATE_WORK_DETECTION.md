# LifeOS Document Brain — Step 11: Detect Duplicate Work

## Goal

Step 11 strengthens Document Brain task conversion so LifeOS does not create a
second task when the document is describing work that is already tracked.

The duplicate comparison now uses:
- title similarity
- description similarity
- existing task status
- optional Gemini semantic similarity

## Semantic behavior

When Gemini embeddings are configured, LifeOS embeds the proposed task meaning
and the existing project task meanings and uses cosine similarity to detect
paraphrases.

Examples:
- "Harden private file access"
- "Enforce document ownership authorization"

can be recognized as overlapping even when the titles use different words.

If semantic embedding configuration/provider access is unavailable, duplicate
review safely falls back to deterministic title + description comparison. Task
creation is never blocked merely because the embedding provider is unavailable.

Set:

    TASK_DUPLICATE_SEMANTIC_ENABLED=0

to explicitly disable semantic duplicate comparison.

## Recommendations

For a strong overlap with an active task:
- Continue existing task

For overlapping work that may need new document details, or a completed task:
- Review and update existing task

When no strong overlap exists:
- Create new task

These are recommendations only. The existing user-controlled Step 9 actions
remain:
- View existing
- Create anyway
- Ignore

## Safety

- Comparison is only against tasks belonging to the selected owned project.
- Existing Step 9 approval checks are still rerun immediately before creation.
- Bulk creation also reruns duplicate assessment.
- No task is silently edited, reopened, linked, or created.
- Similarity component scores remain backend-only; the UI shows only useful
  recommendations.

## Files

Add:
- services/task_duplicate_service.py
- tests/test_task_duplicate_service_step11.py
- tests/test_document_duplicate_step11_compatibility.py
- tests/test_document_duplicate_step11_ui.py

Replace:
- services/document_task_suggestion_service.py
- services/document_task_action_service.py
- templates/_document_task_suggestions.html
- static/css/theme-v2.css

## Database impact

None. No migration is required.
