# LifeOS — Foundation V2

This folder is the safe architecture migration of the latest LifeOS project.

## New direction

- **Backend:** Flask modular monolith
- **API:** versioned `/api/v1`
- **Frontend:** React + TypeScript + Vite, migrated incrementally
- **Database:** PostgreSQL, with Neon as the future hosted target
- **Legacy UI:** preserved until each React replacement has parity

## Start the current backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
python app.py
```

If your existing local database is still SQL Server during the transition, keep
its old environment variables, set `DB_BACKEND=legacy_sqlserver`, and install:

```powershell
pip install -r requirements-legacy-sqlserver.txt
```

## Start local PostgreSQL

From the repository root:

```powershell
docker compose up postgres -d
```

Then set `DATABASE_URL` in `backend/.env`.

## Start React migration frontend

```powershell
cd frontend
npm install
npm run dev
```

The React shell is intentionally not a big-bang replacement. The existing UI is
still the canonical interface until each domain has been migrated safely.

Read `docs/architecture/FOUNDATION_V2.md` before adding new features.
