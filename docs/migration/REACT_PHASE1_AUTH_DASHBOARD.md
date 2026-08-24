# React Migration Phase 1 — Authentication + Dashboard

This phase turns the Vite shell into the first real user-facing slice of LifeOS.

## Included

- React login
- React registration
- React logout
- Flask-Login session reuse
- Flask-WTF CSRF token endpoint and protected unsafe API calls
- protected React routes
- authenticated application shell/sidebar
- API-backed dashboard using the same calculation service as the legacy Jinja dashboard
- private API `no-store` response headers
- Projects / Tasks / Notes / Document Brain / Modules placeholders remain explicit migration boundaries

## Trust boundary

React never receives database, AI provider, or storage credentials. It calls `/api/v1/*` only. Business rules remain in backend services.

## Development

Terminal 1:

```powershell
cd backend
python app.py
```

Terminal 2:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

The Vite dev server proxies `/api/*` to `http://127.0.0.1:5000` so Flask session cookies and CSRF protection work without enabling broad CORS.

## Validation

```powershell
cd backend
python -m pytest tests\test_api_v1_react_phase1.py -v
python -m pytest
```

Then:

```powershell
cd ..\frontend
npm run build
```

## Phase 2

Projects + Tasks are the next React domain. Do not remove the Jinja UI yet.
