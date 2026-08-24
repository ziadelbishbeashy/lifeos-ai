# LifeOS — Full React UI Parity Migration

This package makes React the browser host while preserving the **same existing LifeOS UI and behavior** across the full current product surface.

## Run

### Backend

```powershell
cd backend
python -m pytest tests\test_react_ui_parity_bridge.py -v
python -m pytest
python -m flask --app app db current
python app.py
```

### Frontend

```powershell
cd frontend
npm install
npm run build
npm run dev
```

Open `http://localhost:5173`.

## Browser acceptance pass

Verify at minimum:

1. Landing → Register/Login → Dashboard → Logout.
2. Projects: create, open, edit, delete.
3. Tasks: general/project task create, edit, complete, delete, filters/reminders/recurrence.
4. Focus: start, pause, resume, distraction, review, finish/cancel, insights.
5. Analytics and CSV exports.
6. Notification settings, manual email actions, history.
7. Notes: create, edit, pin, analyze, Ask Note, suggestions, delete.
8. Documents: upload PDF, open document, detect/confirm type, analyze, search, Ask Document.
9. PDF viewer: pages, find, semantic search, selected-context question, download/new-tab fallback.
10. Document task suggestions: approve/edit/link/reject/bulk-create.
11. Project-wide document question/RAG.
12. Compare documents, open saved comparison, rerun comparison.
13. Upload/open a new document version and verify current vs historical behavior.
14. Refresh important pages and confirm the login session remains valid.

## Database

No schema change is required by this frontend architecture migration, so no new Alembic migration is included.
