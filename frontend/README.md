# LifeOS React Frontend — Full UI Parity Host

The active frontend now uses React as the browser host for the full existing LifeOS website while preserving the proven UI and interactions exactly.

## Active path

`src/App.tsx` renders `src/legacy/LegacyScreen.tsx`.

The parity screen:

1. requests the current browser path through `/api/v1/legacy-proxy`;
2. receives the existing trusted Flask controller output;
3. mounts the exact page markup in React;
4. loads the exact existing styles/scripts from `public/static`;
5. bridges forms, PDF/file responses and legacy JavaScript requests back through the API boundary.

There are no active migration placeholder pages.

## Why the old typed React pages are still present

The Phase 1/2 native React pages and typed API clients are intentionally retained as reference code for later component-by-component native conversion. They are not currently routed because the requirement for this migration is **no visible UI or workflow regression**.

## Development

```powershell
npm install
npm run build
npm run dev
```

Run Flask on `127.0.0.1:5000`; Vite proxies `/api` to it.

See `../docs/architecture/REACT_UI_PARITY.md` for the architecture and migration gates.
