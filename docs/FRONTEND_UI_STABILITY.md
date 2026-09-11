# Frontend UI Stability Gate

The React separation exposed a gap in LifeOS reliability: backend pytest and a successful Vite build cannot detect a collapsed grid, blank React screen, or missing interactive Focus controls.

The frontend now has three independent protections:

1. **CSS contract** — one stylesheet entrypoint and an automated guard against reintroducing the obsolete grid shell.
2. **Browser layout/smoke tests** — deterministic Playwright tests mock the JSON API and exercise the actual React DOM in Chromium.
3. **Approved visual snapshots** — pixel regression tests are intentionally enabled only after the UI is visually approved.

The browser fixtures never call Gemini, embeddings, email, the database, or the real backend.  Those remain covered by pytest/integration tests.  Browser tests exist to catch presentation/runtime regressions.

## Stability commands

```bash
cd frontend
npm install
npm run css:check
npx playwright install chromium
npm run test:layout
npm run test:smoke
```

Once visuals are approved:

```bash
npm run test:visual:update
npm run test:visual
```

A UI change is not considered stable if it causes horizontal overflow, collapses the main canvas, throws a React runtime error, or breaks one of the protected critical interactions.
