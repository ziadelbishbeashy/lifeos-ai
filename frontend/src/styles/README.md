# LifeOS frontend CSS ownership

`app.css` is the only stylesheet imported by `src/main.tsx`.

The current UI contains a mature visual foundation that predates the React separation.  The goal of this stabilization phase is **not** to redesign it.  Instead, the cascade is centralized and guarded so a page fix cannot silently collapse another screen.

## Ownership rules

- `react-base.css` — reset/runtime safety only. Never define application grids.
- `lifeos/public.css` — public landing/authentication presentation.
- `lifeos/style.css` — original LifeOS application visual foundation.
- `lifeos/theme-v2.css` — Document Brain and theme refinements.
- `lifeos/project-studio.css` — project workspace-specific styling.
- `lifeos/focus.css` — Focus Studio only.
- `react-native-extras.css` — small React-only components. No shell geometry.
- `visual-parity.css` — React parity details that are not feature-specific.
- `layout-foundation.css` — **canonical geometry contract** for the separated React shell and responsive grids.
- `lifeos/polish.css` — final cosmetic polish only. Do not redefine shell geometry.

`global.css` is an obsolete Phase-2 stylesheet and must remain unreferenced.  It contains the old CSS-grid shell that previously double-counted the sidebar and collapsed the site.

## Before changing layout

Run:

```bash
npm run css:check
npm run test:layout
```

After a visual change, run the Playwright smoke suite.  Once a visual baseline has been approved, update snapshots intentionally with `npm run test:visual:update` and review the image diff before committing.
