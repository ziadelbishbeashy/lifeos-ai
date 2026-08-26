# LifeOS Playwright Smoke Test Fix

This patch fixes two false-negative Playwright smoke tests and hardens the PowerShell stability scripts so native command failures stop the script instead of printing `[10/10] Done`.

## Changes

- `frontend/tests/e2e/smoke/critical-flows.spec.ts`
  - Uses the unique `Project Plan at a glance` heading instead of ambiguous text matching.
  - Uses the first exact `R0 checkpoint` note link because the UI intentionally renders that note in more than one place.
- `scripts/check-react-parity.ps1`
  - Explicitly checks native process exit codes (`python`, `node`, `npm`, `npx`).
  - Stops immediately on a failed pytest/build/audit/Playwright command.
  - Always restores the original PowerShell directory with `try/finally`.
- `scripts/check-frontend-ui.ps1`
  - Adds the same fail-fast behavior.

## Apply

Copy the patch contents over the project root, then run:

```powershell
Unblock-File .\scripts\check-react-parity.ps1
Unblock-File .\scripts\check-frontend-ui.ps1
.\scripts\check-react-parity.ps1
```

Expected browser result:

- 11 layout tests pass.
- 3 smoke tests pass.
- The script reaches `[10/10] Done` only if every prior check succeeded.
