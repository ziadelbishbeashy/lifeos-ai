# React UI Parity Architecture

## Goal

Move the browser entry point to React **without changing the proven LifeOS UI or breaking existing workflows**.

The current LifeOS web surface is large: projects, tasks, notes, Focus Mode, analytics, notifications, Document Brain upload/search/Q&A, PDF navigation, task suggestions, project-wide RAG, document comparison, and versioning. Re-implementing all of those screens and browser scripts in one JSX rewrite would create a large regression surface.

## Current architecture

```text
Browser
  |
  v
React + Vite (browser host)
  |
  | GET/POST /api/v1/legacy-proxy
  | native JSON /api/v1/* where available
  v
Flask application factory
  |
  +-- proven web controllers (compatibility rendering)
  +-- versioned JSON API
  |
  v
Domain/service workflows
  |
  +-- Projects / Tasks / Notes / Focus / Notifications
  +-- Document Brain / RAG / Comparison / Versioning
  |
  v
SQLAlchemy + storage + AI providers
```

## What changed

- React now owns the browser entry point for **every existing LifeOS screen**.
- There are no React migration placeholder pages in the active application.
- The exact legacy HTML/CSS/browser behavior is rendered through a restricted API compatibility bridge.
- Existing Flask workflow controllers and services remain the authority; business logic is not duplicated in React.
- The existing `static/css` and `static/js` assets are copied into `frontend/public/static` so the old appearance and browser behavior are preserved byte-for-byte.
- Unsafe forms still use the existing Flask-WTF CSRF token and session cookie.
- Existing JSON/file interactions used by Focus Mode and the PDF reader are proxied through the same restricted bridge.
- Downloads and PDF file responses continue to come from the existing owned-resource routes.
- The bridge can dispatch only the established browser-facing endpoints; it cannot recurse into `/api` or `/static`.

## Why this is safer than a giant JSX rewrite

This architecture changes the browser host first while preserving the exact UI contract. A later native React conversion can replace one screen at a time behind stable APIs. That gives LifeOS a clean migration seam without forcing Document Brain, Focus, Notes, notifications and analytics to be rewritten simultaneously.

## Native React progression

The previously created typed React Project/Task components remain in the repository as reference work, but the active application uses parity rendering so the visible UI stays identical to the proven interface. When a screen is converted natively, it should meet all of these gates before replacing the parity screen:

1. Visual parity with the existing screen.
2. Full workflow parity, including failure states and confirmation behavior.
3. Ownership isolation tests.
4. Focused API tests.
5. Full pytest.
6. Production frontend build.
7. Browser acceptance checks.

## Runtime

Development:

```powershell
# terminal 1
cd backend
python app.py

# terminal 2
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

Vite proxies only `/api` to Flask. Legacy CSS/JS are served from `frontend/public/static`, while all protected data and actions continue through Flask.

## Important rule

Do not delete `backend/templates`, `backend/routes`, or the proven browser scripts while parity mode is active. They are the compatibility implementation used to guarantee that the architecture change does not silently remove features.
