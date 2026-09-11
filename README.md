# LifeOS — React Frontend / Flask API

LifeOS now uses a fully separated application boundary:

```text
Browser
  -> frontend/  React + TypeScript + Vite
  -> /api/v1/*  JSON / multipart / PDF
  -> backend/   Flask services + domain workflows
  -> SQLAlchemy / SQL Server + AI / RAG
```

## Source-of-truth rule

- **UI, layout, styling, forms, interactions, page navigation:** `frontend/`
- **Business rules, authentication, ownership, persistence, AI/RAG, retrieval, provider handling:** `backend/`
- **Data needed by React:** explicit `/api/v1/*` contracts

The active React application does **not** use `/api/v1/legacy-proxy`, Flask/Jinja-rendered screens, or copied `backend/static` assets. Existing backend templates/static files are compatibility/regression reference only and are not loaded by the React website.

See `FULL_FRONTEND_BACKEND_SEPARATION.md` for the architecture contract.

## Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
python app.py
```

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Complete reliability gate

From the project root:

```powershell
.\scripts\check-react-parity.ps1
```

The historical script name is preserved so existing workflows keep working, but it now checks the **full frontend/backend separation contract**, full backend regression, migration head, frontend source references, Vite build, and production dependency audit.

## Database migrations

The frontend separation itself changes no database schema, so no Alembic migration is added for this architecture change.
