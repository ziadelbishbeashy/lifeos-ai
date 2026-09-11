# LifeOS React Native Parity — Projects Slice

This patch migrates **only the `/projects` index screen** from the React/Jinja compatibility bridge to a native React + JSON API implementation while preserving the proven LifeOS UI and existing backend workflows.

## Architecture after this patch

```text
/projects
Browser -> React ProjectsPage -> /api/v1/projects -> project facade/service -> SQLAlchemy

All other screens
Browser -> React LegacyScreen -> /api/v1/legacy-proxy -> existing Flask/Jinja controllers
```

The Project Studio route (`/projects/<id>`), Tasks, Notes, Document Brain, Focus, Analytics and notifications settings remain on the compatibility layer for now. This is intentional: each screen is migrated only after its own parity checks pass.

## UI parity preserved on `/projects`

- exact old LifeOS application shell classes and structure
- sidebar/navigation
- theme switch
- local notification center
- profile menu + confirmed logout
- project summary cards
- project search/status/priority filters
- project health labels
- task-driven progress
- open-task count
- note count
- next action
- project deadline
- new-project modal and all existing fields
- no-deadline behavior
- old loading overlay/navigation behavior

The existing `style.css`, `theme-v2.css`, `project-studio.css` and `main.js` are reused from `backend/static` and synchronized to `frontend/public/static` by the existing `sync:legacy-ui` script.

## Important backend change

`GET /api/v1/projects` now exposes the product-level fields the old project cards require (`goal`, `description`, `project_type`, `tech_stack`, `current_phase`, `note_count`, etc.). It still does **not** expose chunk IDs, embeddings, retrieval scores, provider internals, or other RAG implementation details.

No database schema or Alembic migration is required.

## Apply

For the patch ZIP, copy/overwrite the files into the root of your current `lifeos-ai` project. The patch does not touch AI/RAG provider code, document workflows, migrations, or database models.

## Verify

From the project root:

```powershell
.\scripts\check-react-parity.ps1
```

Expected important checks:

- React parity bridge tests pass
- React API tests pass
- full pytest passes
- migration head remains `20260811_0002 (head)` unless your local project intentionally has a newer migration
- Vite production build succeeds

Then run:

```powershell
# terminal 1
cd backend
python app.py
```

```powershell
# terminal 2
cd frontend
npm run dev
```

Open `http://localhost:5173/projects`.

## Browser acceptance checklist

1. Projects page looks the same as the old Projects page.
2. Sidebar/topbar/theme/profile/notifications still work.
3. Search filters project title, goal/description, type, tech stack and phase.
4. Status and priority filters work.
5. Clear filters works.
6. `+ New Project` opens the same modal.
7. `No deadline` disables/clears the deadline input.
8. Create a project and verify it appears after the page reload.
9. Invalid project input shows the backend validation message and does not create data.
10. `Open Project` still opens the existing Project Studio screen.
11. In the Flask terminal, loading `/projects` should use `GET /api/v1/projects` and should **not** require `GET /api/v1/legacy-proxy` for the Projects index itself.
12. Other screens may still show `legacy-proxy`; that is expected until their own migration slices are completed.

## Files changed

- `frontend/src/App.tsx`
- `frontend/src/main.tsx`
- `frontend/src/api/types.ts`
- `frontend/src/pages/ProjectsPage.tsx`
- `frontend/src/native/NativeWorkspaceShell.tsx`
- `frontend/src/native/useNativeLegacyAssets.ts`
- `backend/lifeos/api/v1/serializers.py`
- `backend/lifeos/api/v1/routes.py`
- `backend/tests/test_api_v1_react_phase2.py`

