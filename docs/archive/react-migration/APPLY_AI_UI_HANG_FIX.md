# LifeOS React Parity — AI Loading Fix

This patch fixes two React parity-host issues that can make working AI/RAG actions look stuck even after Flask finishes successfully.

## What was happening

1. **Ask Document** saves the answer and Flask redirects back to the same document with `#ask-document`.
   The parity bridge converted that redirect to a `204` + `X-LifeOS-Legacy-Redirect` header. Because the destination is the same path with only a hash change, normal browser assignment did not force React to reload the persisted answer. The old loading state therefore stayed visible.

2. **Detect Document Type** intentionally returns a freshly rendered HTML page containing a transient, not-yet-confirmed type-detection result. The parity host previously discarded that returned HTML and did a normal GET reload. The detection result therefore vanished instead of appearing for confirmation.

## Changed files

- `frontend/src/legacy/legacyBridge.ts`
- `frontend/src/legacy/LegacyScreen.tsx`

No backend AI/RAG service, database model, migration, prompt, retrieval logic, or Gemini configuration is changed.

## Fix behavior

- Same-screen Flask redirects now force a real reload while preserving the target hash.
- Successful legacy POSTs that directly return HTML are preserved for exactly one reload in `sessionStorage`, then consumed and deleted immediately. This lets transient server-rendered results such as document-type detection appear exactly once, just as they did before the React host migration.
- The staged page expires after 60 seconds and is removed before parsing, preventing reload loops.

## Apply

Copy the two files from this patch into the matching paths of your current LifeOS project, replacing the existing versions.

Then run from the project root:

```powershell
.\scripts\check-react-parity.ps1
```

Restart the frontend after the build:

```powershell
cd frontend
npm run dev
```

The Flask backend may remain running, but restarting it is fine as well.

## Browser checks

### Detect document type

1. Open a PDF that has extracted text.
2. Click **Detect document type**.
3. Wait for the provider call to finish.
4. The detected-type confirmation panel should appear instead of returning to the unchanged page.
5. Confirm/change the type and continue to analysis.

### Ask Document

1. Open the document's **Ask document** tab or use selected PDF context.
2. Ask a question.
3. Wait for the backend logs to reach `question_saved`.
4. The browser should reload the same document, keep/open `#ask-document`, and show the saved answer.
5. The loading overlay/button must not remain stuck.

## Important diagnostic rule

If Flask logs reach `question_saved` and the POST returns `204`, the RAG workflow completed. A spinner that remains after that point is a frontend navigation/parity problem, not a retrieval/model failure.
