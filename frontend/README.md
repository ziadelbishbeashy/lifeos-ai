# LifeOS React Frontend — Migration Phase 1

The React application is now a real LifeOS client for the first migration slice:
public landing, login, registration, authenticated shell, logout, and the live
execution dashboard.

The backend remains canonical for business rules. React calls the versioned
`/api/v1` boundary; it does not access the database or AI providers directly.

## Development

Run the backend first:

```powershell
cd backend
python app.py
```

Then run React in another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

Vite proxies `/api/*` to `http://127.0.0.1:5000`, preserving Flask-Login session
cookies and Flask-WTF CSRF protection without opening broad CORS access.

## Current React parity

- Landing page
- Login
- Registration
- Logout
- Protected application shell
- Dashboard

Projects, Tasks, Notes and Document Brain still display explicit migration
placeholders. Their proven backend implementations remain available until each
API + React replacement passes its own regression tests.
