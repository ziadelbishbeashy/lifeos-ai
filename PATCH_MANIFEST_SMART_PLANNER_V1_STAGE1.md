# V-SPACE AI — Smart Planner V1 Stage 1

## Purpose
This patch adds the first real Smart Planner vertical slice without creating a second intelligence stack.

Flow:

`owned workspace state -> deterministic preview -> user review -> I9 proposal -> explicit confirmation -> deterministic plan persistence`

The planner never asks an LLM to perform exact time arithmetic and no AI component writes planner rows directly.

## Included behavior

### Planner UI
- New `/planner` React page.
- New **Smart Planner** entry under the existing Planning navigation group.
- Day / Week mode.
- Start date selector.
- Optional project scope.
- Working start/end hours.
- Configurable break length.
- Optional planning-goal text.
- Timeline view with scheduled task blocks.
- Workload/capacity cards.
- Explicit overload/unscheduled section.
- Responsive desktop/tablet/mobile layout.
- Light/dark theme compatibility.

### Deterministic planning
The backend ranks only owned, open tasks using reviewed deterministic signals:
- task importance;
- task/project deadline urgency;
- existing priority score;
- blocked-task penalty;
- task difficulty for duration estimates;
- bounded lexical match against the optional planning goal.

V1 duration defaults:
- Easy: 30 minutes
- Medium: 60 minutes
- Hard: 90 minutes

If the work does not fit, Smart Planner leaves tasks unscheduled and reports the overload. It does not compress or hide excess work.

### I9 confirmation boundary
`POST /api/v1/planner/preview` is read-only.

`POST /api/v1/planner/proposals` recomputes the preview on the server and creates a pending `apply_smart_plan` I9 proposal only.

The existing confirmation endpoint remains the mutation boundary:

`POST /api/v1/intelligence/action-proposals/<proposal_id>/confirm`

Only after explicit confirmation are `SmartPlannerPlan` and `SmartPlannerBlock` rows persisted.

### Persistence
Adds:
- `smart_planner_plans`
- `smart_planner_blocks`

Migration:
- `20260911_0001_add_smart_planner_v1.py`
- new expected Alembic head: `20260911_0001`

This is an intentional schema change required to persist accepted schedules.

### API
- `GET /api/v1/planner`
- `POST /api/v1/planner/preview`
- `POST /api/v1/planner/proposals`

Existing I9 confirm/dismiss endpoints are reused.

## Tests added
`backend/tests/test_smart_planner_v1.py`

Coverage includes:
1. preview remains read-only;
2. urgent work is prioritized;
3. no plan row exists before I9 confirmation;
4. confirmed proposal creates the accepted plan/blocks;
5. overload is reported instead of overfilling time;
6. project filters remain ownership-bounded.

## Validation performed in this sandbox
Passed:
- Python compile/static syntax for every modified/new backend Python file.
- TypeScript isolated transpile/syntax for `SmartPlannerPage.tsx`, `App.tsx`, and `NativeWorkspaceShell.tsx`.
- `npm run css:check` after extending the intentional CSS contract.
- source scan: no `eval`, `exec`, or `dangerouslySetInnerHTML` added.

Blocked by sandbox dependencies:
- `pytest` cannot start because Flask is not installed in this sandbox (`ModuleNotFoundError: flask`).
- full `npm run build` cannot run because `node_modules` is not installed in this sandbox.

## Run locally after applying
Backend:

```powershell
cd backend
py -3.11 -m pytest -q tests/test_smart_planner_v1.py
py -3.11 -m pytest -q
```

Database:

```powershell
flask db upgrade
flask db current
```

Expected head: `20260911_0001`

Frontend:

```powershell
cd frontend
npm ci
npm run build
npm run css:check
```

## Stage 1 boundaries / next Smart Planner patch
Deliberately not included yet:
- fixed calendar/academic commitments as blocked time;
- drag/drop or manual block editing;
- one-click rebalancing after a missed block;
- Goal Plan mode;
- user timezone/planning-preference persistence;
- AI-generated rationale beyond deterministic planner signals;
- Private Tutor -> Smart Planner study-block suggestions.

These should build on this same planner service and I9 boundary rather than create parallel scheduling logic.
