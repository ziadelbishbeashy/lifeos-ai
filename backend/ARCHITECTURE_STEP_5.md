# LifeOS Architecture Step 5 — Projects Refactor

This checkpoint moves project business logic out of Flask routes while
preserving the current URLs, templates, database schema, and user experience.

## Added

- `services/project_service.py`
  - Project form normalisation and validation
  - Ownership-safe project queries
  - Create, update, and delete transactions
  - Projects-page and Project Studio view models
  - Deterministic project health and next-task calculations
- `tests/test_project_service.py`
- `tests/test_projects.py`

## Updated

- `routes/project_routes.py`
  - Routes now handle HTTP concerns only
  - Database errors use structured application logging
  - Cross-user project access returns a neutral 404

## Security improvements

- Every project read and write is scoped by `user_id`.
- Project cards and project details also filter related tasks and notes by the
  signed-in user as defence in depth.
- Status and priority values are validated before persistence.
- Database transactions roll back on SQLAlchemy errors.

## Database impact

None. This step does not add, remove, or alter any table or column.

## Verification

Run:

```powershell
python -m pytest
python app.py
```

Then test project creation, editing, opening, and deletion.
