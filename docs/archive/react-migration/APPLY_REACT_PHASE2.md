# LifeOS React Migration — Phase 2

This checkpoint migrates **Projects, Tasks, and the core Project Studio** to the
React + TypeScript client while keeping Flask services authoritative.

## What changed

### Backend API architecture

API v1 is now split by product boundary instead of growing one route file:

- `lifeos/api/v1/routes.py` — auth/session/dashboard/core metadata only
- `lifeos/api/v1/projects.py` — Project CRUD + Project Studio read model
- `lifeos/api/v1/tasks.py` — Task CRUD + completion toggle
- `lifeos/api/v1/documents.py` — safe current-document listing during migration
- `lifeos/api/v1/common.py` — shared JSON/auth/error helpers
- `lifeos/api/v1/serializers.py` — explicit product-safe JSON contracts

Routes reuse the existing domain facades/services. Business validation,
ownership, persistence, recurrence, reminders, cascades, and transaction rules
stay in the backend.

### React

The following placeholders are now real React workspaces:

- `/projects`
- `/projects/:projectId`
- `/tasks`

The frontend uses TanStack Query for server state and invalidation. Project and
task mutations refresh dashboard/project/task queries instead of forcing full
page reloads.

## Intentionally unchanged

- No database table/column changes.
- No Alembic revision is required.
- Notes remain on the existing backend/Jinja workflow.
- Advanced Document Brain (upload, Ask Document, analysis, citations, PDF
  navigation, RAG, comparison, versioning) remains on the proven backend until
  its dedicated React slice.
- `backend/templates` and `backend/static` are still preserved as the reference
  UI until parity is proven.

This follows the master-plan rule to prefer smaller reviewable migrations over a
large blind rewrite.

## Verification

Backend:

```powershell
cd backend
python -m compileall -q .
python -m pytest tests\test_api_v1_react_phase1.py -v
python -m pytest tests\test_api_v1_react_phase2.py -v
python -m pytest
python -m flask --app app db current
python app.py
```

Frontend:

```powershell
cd frontend
npm install
npm run build
npm run dev
```

Browser acceptance:

1. Login and open `/projects`.
2. Create, edit, open, and delete a test project.
3. Open a project and create/edit/complete/delete a project task.
4. Open `/tasks` and create a general task and a project task.
5. Filter by status/scope and edit/toggle/delete tasks.
6. Refresh the browser and confirm the Flask session survives.
7. Confirm the dashboard updates after mutations.
8. Confirm the legacy Flask UI still works at port 5000.

## Next migration slice

Notes should be migrated next. Document Brain should remain a separate later
slice because it carries the highest trust and regression risk.
