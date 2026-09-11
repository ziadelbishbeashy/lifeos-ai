# I21 Academic Schedule — patch

This is a patch-only replacement package built on top of the I20 Experience Profiles baseline.
It does not include `frontend/public` and does not create a second Student application.

## What this patch completes

- `ModuleAssessment` is a first-class child of the existing `LearningModule`.
- Assessment types: Quiz, Assignment, Midterm, Final, Project, Presentation, Lab, Other.
- Stored facts: dates/times, due dates/times, weight, status, topics, prep estimate, notes.
- Deterministic facts: target date, days until, timing label (Today/Tomorrow/This week/Overdue).
- Ownership-safe CRUD service; an assessment cannot be mutated through another module URL or another user's module.
- React API/types for assessment CRUD.
- Student-only assessment emphasis inside the existing Module Details page (no new sidebar/page).
- Module cards and summary strip show assessment counts for Student-enabled profiles.
- Create, edit, complete, and remove assessment UI.
- I21 regression tests for auth, validation, CRUD, ownership, parent-module isolation, deterministic timing, module serialization, and delete.

## Architecture

React Module Details
→ `/api/v1/modules/<module_id>/assessments`
→ `services/module_assessment_service.py`
→ `ModuleAssessment`
→ MSSQL

Experience Profiles only change UI emphasis. Backend ownership remains the canonical security boundary.

## Migration

New head:

`20260901_0001 -> 20260901_0002`

Run from `backend`:

```powershell
py -3.11 -m alembic -c migrations/alembic.ini upgrade head
py -3.11 -m alembic -c migrations/alembic.ini current
```

Expected head: `20260901_0002`.

## Tests

Backend:

```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\backend
py -3.11 -m pytest tests\test_module_assessments_i21.py -q
py -3.11 -m pytest -q
```

Frontend:

```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\frontend
npm run build
npm run css:check
```

## Important scope

This patch completes the manual Academic Schedule foundation and React experience. PDF/syllabus extraction, Ask LifeOS academic-context integration, and Today/weekly planner consumption are deliberately left as the next I21 integrations so they can reuse this verified assessment model instead of introducing a second schedule store.
