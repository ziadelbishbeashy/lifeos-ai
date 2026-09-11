# LifeOS React Migration — Phase 1

Apply this patch over the **clean Foundation V2 root**. It does not contain or
replace `backend/.env`, local uploads, or `backend/instance` data.

## What this phase migrates

- Public React landing page
- React login
- React registration
- Flask-Login session reuse
- Flask-WTF CSRF-protected JSON mutations
- React logout
- Protected React application shell
- Live React dashboard backed by the same dashboard service used by Jinja
- API private/no-cache hardening
- 8 new backend API contract/regression tests

Projects, Tasks, Notes and Document Brain remain explicit placeholders for the
next migration phases. Their existing backend/Jinja workflows are untouched.

## Apply

Extract this ZIP into the LifeOS repository root and allow matching files to be
replaced.

Do **not** delete `backend/templates` or `backend/static` yet.

## Run

Terminal 1:

```powershell
cd backend
python -m pytest tests\test_api_v1_react_phase1.py -v
python -m pytest
python app.py
```

Your previous suite had 446 passing tests. This patch adds 8 tests, so a fully
collected unchanged suite should normally be around 454 tests, although the
exact count is less important than zero failures.

Terminal 2:

```powershell
cd frontend
npm install
npm run build
npm run dev
```

Open:

```text
http://localhost:5173
```

The Vite server proxies `/api/*` to `http://127.0.0.1:5000`.

## Browser smoke test

1. Open `/` while logged out and confirm the React landing page appears.
2. Register a test account or log in with an existing account.
3. Confirm `/dashboard` shows real backend counts, projects and tasks.
4. Refresh the browser and confirm the session survives.
5. Log out and confirm protected routes return to the login screen.
6. Confirm `localhost:5000` still works as the legacy/reference UI.

## Do not do yet

- Do not remove Jinja/templates.
- Do not switch database engines in the same change.
- Do not start OCR/Modules in this patch.

Next React phase: Projects + Tasks.
