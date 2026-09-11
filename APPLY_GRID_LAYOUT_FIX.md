# LifeOS — Full-site grid/layout repair

This patch fixes the collapsed/narrow React layout without undoing frontend/backend separation.

## Root cause
The separated frontend was loading two incompatible shell systems at once:

- the original LifeOS CSS expects a **fixed 280px sidebar** and an `.app-main` offset with `margin-left: 280px`;
- the obsolete Phase-2 `global.css` also made `.app-shell` a **two-column CSS grid**.

The sidebar was therefore counted twice. The remaining React canvas collapsed, which made headings wrap almost character-by-character and broke grids across Dashboard, Projects, Tasks, Notes, Analytics and Document Brain.

## What this patch does

1. Stops importing the obsolete `frontend/src/styles/global.css`.
2. Replaces it with a tiny React reset (`react-base.css`).
3. Preserves the few React-only component rules that were actually needed (`react-native-extras.css`).
4. Adds `layout-foundation.css`, loaded last, to enforce one layout model across the whole private app.
5. Adds explicit responsive safety for dashboard, project, task, notes, analytics and Document Brain grids.
6. Adds a layout-contract check to `scripts/check-react-parity.ps1` so the conflicting shell cannot be accidentally reintroduced.

## Apply
From the ZIP, copy `frontend` and `scripts` over the matching folders in your current project.

Then from the project root:

```powershell
Unblock-File .\scripts\check-react-parity.ps1
.\scripts\check-react-parity.ps1
```

Then restart both servers:

```powershell
cd backend
python app.py
```

and in another terminal:

```powershell
cd frontend
npm run dev
```

Hard-refresh the browser (`Ctrl+F5`).

## Visual acceptance order
Check at desktop width first:

1. Dashboard — hero spans the content canvas; 4 statistics form a row; main panels are 2 columns.
2. Projects — summary cards form a row and project cards use two columns where space allows.
3. Tasks — filters use the full row and task cards span the canvas.
4. Notes — note grid uses three columns on wide screens.
5. Analytics — six summary cards and the primary two-column analytics grid render correctly.
6. Document Brain — upload row and three-column document grid use the available canvas.
7. Resize below 980px — sidebar becomes off-canvas and content becomes full width.
8. Resize below 760px — content grids become single-column without horizontal overflow.

The backend/API/RAG/database files are not changed by this patch.
