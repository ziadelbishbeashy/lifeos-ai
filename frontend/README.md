# LifeOS React Frontend

This folder is the **only active UI source of truth** for LifeOS.

## Architecture

```text
Browser
  -> React + TypeScript + Vite (this folder)
  -> /api/v1/* JSON/file endpoints
  -> Flask backend services
  -> SQLAlchemy / SQL Server / AI / RAG
```

UI/layout/style changes belong in `frontend/` only. The React application does not render Flask/Jinja pages, does not call `/api/v1/legacy-proxy`, and does not copy `backend/static` during dev/build.

### UI source

- `src/pages/` — route-level React screens
- `src/components/` — shared UI controls, including the compact Verify evidence control
- `src/features/` — project/task forms and API helpers
- `src/styles/lifeos/` — the established LifeOS visual foundation, now frontend-owned
- `src/styles/separated.css` — React-native/separation-specific styles
- `src/api/` — JSON API client and types
- `src/core/navigation.ts` — small same-origin navigation helper

`archive/pre-separation/` contains old migration references only. It is outside `src`, is not built, and is not required by the application.

## Development

```powershell
npm install
npm run dev
```

The Vite dev server proxies `/api/*` to `http://127.0.0.1:5000`.

## Build

```powershell
npm run build
```

No legacy asset synchronization step exists anymore.
