# Apply — Full LifeOS Frontend / Backend Separation

Use the patch ZIP over your current stable `lifeos-ai` folder. It is intentionally based on the latest React parity + Document Analysis redesign line and keeps the backend service/RAG architecture intact.

## 1. Back up / commit your current stable state

```powershell
git status
git add .
git commit -m "Checkpoint before full frontend separation"
```

## 2. Extract the patch over the project root

Allow replacement of files in the patch. The patch contains changed/new files only.

## 3. Remove obsolete parity files

Run from the project root:

```powershell
.\scripts\apply-full-separation-cleanup.ps1
```

This removes the old active legacy bridge/router/static-sync files that a ZIP overlay cannot delete by itself.

## 4. Install frontend dependencies

```powershell
cd frontend
npm install
cd ..
```

`react-router-dom` is no longer required and `sync:legacy-ui` is gone.

## 5. Run the complete gate

```powershell
.\scripts\check-react-parity.ps1
```

Expected architectural checks:

- `/api/v1/legacy-proxy` returns 404
- active `frontend/src` contains no legacy proxy reference
- active frontend contains no `react-router-dom` reference
- no backend-static synchronization script is used
- full pytest passes
- Alembic head remains current
- Vite production build passes
- `npm audit --omit=dev` passes

## 6. Start the app

Backend:

```powershell
cd backend
python app.py
```

Frontend:

```powershell
cd frontend
npm run dev
```

Open `http://localhost:5173`.

## Browser acceptance

Check: login, dashboard, Projects CRUD, Project Studio/tasks, project RAG, Notes + AI, Focus, Analytics/CSV, Notifications, PDF upload/view/search, Detect Type, Analyze, Verify source, Ask Document, document actions, Compare, Versions, logout.

## UI rule after this patch

A visual change belongs in `frontend/`. Do not edit `backend/templates` or `backend/static` to change the active React website.
