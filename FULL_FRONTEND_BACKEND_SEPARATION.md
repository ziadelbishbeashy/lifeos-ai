# LifeOS — Full Frontend / Backend Separation

## Checkpoint

The active application architecture is now:

```text
frontend/ React + TypeScript + CSS
        |
        | HTTP JSON / multipart / PDF
        v
backend/ /api/v1/*
        |
        v
services / domains
        |
        +--> SQLAlchemy / SQL Server
        +--> AI providers / RAG / retrieval
```

## Ownership rule

**Change appearance, page structure, interaction, forms, cards, tabs, dialogs, or client navigation:** edit `frontend/`.

**Change business rules, persistence, ownership/security, AI prompts/workflows, retrieval, embeddings, or provider behavior:** edit `backend/`.

**Change data required by a screen:** add/change an explicit `/api/v1/*` contract in the backend, then consume it in the frontend.

## Removed from the active frontend

- `/api/v1/legacy-proxy`
- Flask/Jinja rendering as a React screen source
- `backend/static -> frontend/public/static` copying
- `sync:legacy-ui`
- React Router v6 dependency

The old Flask templates/static files can remain temporarily as compatibility/regression reference, but the React app does not load them. They are no longer the UI source of truth.

## Native React areas

- Landing / login / register
- Dashboard
- Projects / Project Studio
- Tasks
- Notes + note AI
- Focus + focus insights
- Analytics + CSV exports
- Notifications settings/history/email actions
- Document Brain list/upload
- Document details and redesigned analysis UX
- Compact Verify evidence control
- PDF viewer
- Direct document search
- Detect type / analyze
- Ask Document
- Ask Project / multi-document RAG
- Document task suggestions
- Document comparisons
- Document version history/new version upload

## Stability gate

Run from project root:

```powershell
.\scripts\check-react-parity.ps1
```

Despite the historical filename, this script now validates the separated architecture. It checks the new separation contract, API regression, full pytest suite, migration head, source references, Vite build, and production npm audit.
