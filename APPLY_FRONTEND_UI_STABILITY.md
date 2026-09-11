# Apply — Frontend UI Stability + Playwright Regression Gate

This update is based on the latest `lifeos-ai-feature-hybrid-rag (4)` repository snapshot.

It does **not** redesign LifeOS and does not change Flask/RAG/database behavior.  It stabilizes the separated React frontend so future work cannot silently reintroduce the grid collapse, blank Document Brain screen, or reduced Focus Studio behavior.

## What changed

- One authoritative CSS entrypoint: `frontend/src/styles/app.css`
- Obsolete Phase-2 `global.css` removed
- CSS/layout contract checker added
- Playwright browser regression framework added
- Desktop/tablet/mobile layout checks added
- Critical Focus Studio interaction smoke test added
- Document Brain blank-page + Detect Type + Ask AI + Verify smoke test added
- Projects/Tasks/Notes browser smoke coverage added
- Screenshot regression suite added, but baselines stay opt-in until the UI is visually approved
- GitHub Actions now runs browser layout/smoke checks
- Visual CI automatically starts once approved PNG baselines are committed
- `check-react-parity.ps1` now includes CSS and browser regression checks

## Apply the patch

Copy the patch contents over your current LifeOS root, then from PowerShell:

```powershell
Unblock-File .\scripts\apply-ui-stability-cleanup.ps1
Unblock-File .\scripts\check-react-parity.ps1
.\scripts\apply-ui-stability-cleanup.ps1
.\scripts\check-react-parity.ps1
```

The first Playwright run may download Chromium once.

## Fast frontend-only check

```powershell
.\scripts\check-frontend-ui.ps1
```

## Visual snapshots

Do **not** freeze snapshots until you are happy with how the current UI looks.

After you visually approve Dashboard, Projects, Tasks, Focus and Document Brain:

```powershell
cd frontend
npm run test:visual:update
npm run test:visual
```

Review the generated screenshots and then commit the `*-snapshots` PNG files.  CI will automatically begin enforcing screenshot diffs after those baselines exist.

## Architecture stays separated

```text
frontend/
  React UI + CSS + browser tests
        ↓ JSON
backend/
  Flask APIs + services + DB + AI/RAG
```

No legacy proxy or backend-static sync is reintroduced.
