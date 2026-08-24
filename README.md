# LifeOS — Foundation V2 + React UI Parity

This repository keeps the proven LifeOS backend workflows intact while making React + TypeScript + Vite the browser host for the **entire current website**.

## Architecture

- **Browser host:** React + TypeScript + Vite
- **Backend:** Flask modular monolith / application factory
- **API:** versioned `/api/v1`
- **UI parity bridge:** restricted `/api/v1/legacy-proxy`
- **Database:** SQLAlchemy with PostgreSQL as the preferred target
- **Document Brain:** existing trusted services remain unchanged
- **Old visual design:** preserved exactly through the existing CSS/JS assets

The active React app has no migration placeholders. Projects, Tasks, Notes, Focus Mode, Analytics, Notifications and the existing Document Brain screens can all be opened through the React host while continuing to use the proven Flask workflow/controller logic.

See `docs/architecture/REACT_UI_PARITY.md` for the migration design and safety rules.

## Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
python -m pytest tests\test_react_ui_parity_bridge.py -v
python -m pytest
python -m flask --app app db current
python app.py
```

If the current local database is still SQL Server during the transition, keep the existing legacy database environment values and follow the repository's SQL Server compatibility requirements.

## Frontend

```powershell
cd frontend
npm install
npm run build
npm run dev
```

Open `http://localhost:5173`.

`npm run dev` and `npm run build` automatically synchronize the proven backend CSS/JS into `frontend/public/static`, preventing the React host from visually drifting from the existing UI.

## Database migrations

This UI architecture change does not alter the database schema, so it intentionally contains no new Alembic migration.
