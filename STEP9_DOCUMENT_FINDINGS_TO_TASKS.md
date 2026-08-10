# LifeOS Document Brain — Full Step 9

## Goal

Convert supported Document Brain findings into real LifeOS tasks only after
explicit user confirmation.

This implementation follows the locked product decisions:

- Suggestions appear in **Document → Actions** and on the linked **Project** page.
- The user can create one suggestion or multi-select safe suggestions and create
  them together.
- Every normal suggestion offers **Create**, **Edit first**, and **Ignore**.
- A possible duplicate offers **View existing**, **Create anyway**, and **Ignore**.
- Created suggestions remain visible as **Created**; ignored suggestions remain
  visible as **Ignored**.
- New tasks default internally to `Pending`, shown as **To Do** in the review
  form, but the user can change status before creation.
- Editable fields before creation are title, description, priority, due date,
  tags, status, and project.
- Source document/page/section/evidence remain trusted provenance and cannot be
  edited from the task review form.

## Main flow

Document analysis → grounded action items → persistent suggestions → user review
→ duplicate check → explicit confirmation → real task.

No task is created merely because an AI analysis ran.

## Duplicate behavior

Step 9 uses the existing deterministic task-title similarity check as a safety
boundary. The check is refreshed immediately before task creation so it does not
rely only on the state that existed when the PDF was analysed.

Bulk creation deliberately skips possible duplicates. Those suggestions remain
in review so the user can inspect the existing task and deliberately choose
Create anyway if appropriate.

The later roadmap duplicate-work step can improve this with description/status
and semantic similarity without changing the Step 9 confirmation UI.

## Suggestion lifecycle

Database compatibility is preserved:

- `Pending` → user-facing **Suggested**
- `Approved` → user-facing **Created**
- `Linked` → user-facing **Existing task**
- `Rejected` → user-facing **Ignored**

The older internal values remain so previous suggestion records and tests remain
compatible.

## Tags schema change

Step 9 adds nullable `tags` columns to:

- `tasks`
- `document_task_suggestions`

Tags are normalized as a comma-separated list, deduplicated case-insensitively,
limited to 12 tags for tasks, and do not affect existing rows.

Run the Alembic migration before restarting the application:

```powershell
python -m flask --app app db current
python -m flask --app app db upgrade
```

For SQL Server environments that intentionally do not run Alembic directly,
`sql/step9_document_task_conversion.sql` contains an idempotent alternative.
Do not run both approaches for the same deployment.

## Important files

### Database/model
- `models.py`
- `migrations/versions/20260810_0001_add_task_tags.py`
- `sql/step9_document_task_conversion.sql`

### Services
- `services/document_task_action_service.py`
- `services/document_task_suggestion_service.py`
- `services/document_analysis_service.py`
- `services/task_service.py`
- `services/project_service.py`
- `services/recurring_task_service.py`
- `services/ai_service.py`

### Routes
- `routes/document_routes.py`
- `routes/project_routes.py`

### UI
- `templates/_document_task_suggestions.html`
- `templates/document_suggestion_edit.html`
- `templates/document_details.html`
- `templates/project_details.html`
- `templates/tasks.html`
- `templates/edit_task.html`
- `static/js/document-task-suggestions.js`
- `static/js/main.js`
- `static/css/theme-v2.css`

## Test commands

```powershell
python -m py_compile `
    models.py `
    services\document_task_action_service.py `
    services\document_task_suggestion_service.py `
    services\document_analysis_service.py `
    services\task_service.py `
    services\project_service.py `
    services\recurring_task_service.py `
    routes\document_routes.py `
    routes\project_routes.py

node --check static\js\document-task-suggestions.js
node --check static\js\main.js

python -m pytest `
    tests\test_document_task_action_service.py `
    tests\test_document_task_suggestion_service.py `
    tests\test_document_task_conversion_step9.py `
    tests\test_document_task_conversion_step9_ui.py `
    tests\test_task_tags_step9.py `
    -v

python -m pytest
```

## Manual smoke test

1. Open a linked PDF with completed analysis.
2. Open **Actions**.
3. Confirm suggestions are visible.
4. Create one suggestion directly.
5. Confirm it stays visible as **Created**.
6. Use **Edit first** on another suggestion and change project, status, tags,
   priority, deadline, title, and description.
7. Confirm trusted PDF provenance is not editable.
8. Select several non-duplicate suggestions and use **Create selected**.
9. Add an existing project task with a similar title, then verify the suggestion
   changes to the possible-duplicate review flow.
10. Open the linked Project page and confirm the same document suggestions are
    visible there.
