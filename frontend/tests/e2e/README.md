# LifeOS browser regression tests

These tests deliberately mock `/api/v1/*` at the browser boundary.  They test the separated React frontend deterministically without calling the real database, Gemini, embeddings, email or RAG providers.

The backend has its own pytest/integration suite.  Together the two layers catch different failures:

- pytest: service/API/data/ownership/RAG contracts
- Playwright: React crashes, blank pages, collapsed grids, responsive overflow and critical user interactions

## First-time setup

```bash
npm install
npx playwright install chromium
```

## Fast checks

```bash
npm run css:check
npm run test:layout
npm run test:smoke
```

## Visual baselines

Do **not** create a visual baseline until the UI has been visually reviewed and approved.  A baseline freezes what the product looks like, including mistakes.

Once approved:

```bash
npm run test:visual:update
npm run test:visual
```

Commit the generated `*-snapshots/*.png` files.  CI automatically starts enforcing screenshot diffs once those images exist.
