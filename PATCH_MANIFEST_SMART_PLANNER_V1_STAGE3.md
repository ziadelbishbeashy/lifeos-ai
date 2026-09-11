# V-SPACE AI — Smart Planner V1 Stage 3

## Purpose
Stage 3 adds natural-language planner understanding without introducing a second intelligence stack or allowing an LLM to write schedules directly.

The flow remains:

`user language -> high-confidence structured constraints -> deterministic scheduler -> read-only preview -> I9 proposal -> explicit confirmation -> deterministic persistence`

## Added

### Natural-language planning
New service:

- `backend/services/smart_planner_language_service.py`

It deterministically understands high-confidence planning language including:

- today / tomorrow
- day / week / N-day goal horizons
- light / normal / intense day intent
- fixed time such as `university until 2 PM`
- explicit ranges such as `meeting from 10 AM to 11 AM`
- focus durations such as `3 hours for V-SPACE`
- study durations such as `90 minutes for calculus`
- priority phrases such as `make sure I finish deployment`
- replan / rebalance language such as `I missed the morning. Replan the rest of today.`

Ambiguous language is **not invented into calendar facts**. It remains ordinary request text for prioritisation.

### New planner endpoints

- `POST /api/v1/planner/natural-preview`
- `POST /api/v1/planner/natural-proposals`

Natural preview is read-only. Natural proposals still require the existing I9 confirmation endpoint before an accepted plan changes.

### Prompt-derived plan-local blocks
Two safe block types are supported:

- `focus` — explicit user-requested focus time
- `inferred_commitment` — high-confidence unavailable time extracted from the prompt

Inferred commitments are locked inside the accepted plan, but they are **not silently copied into permanent recurring commitments**.

### Light-day planning
Prompts such as:

`I'm tired today, give me a lighter plan.`

reserve part of available capacity instead of filling the day completely.

### Natural rebalancing
Prompts such as:

`I missed the morning. Replan the rest of today.`

reuse the current accepted plan and protect elapsed time. Locked blocks remain fixed. Existing requested focus time is carried into the rebalance rather than disappearing.

### UI
Smart Planner now:

- uses natural-language planning automatically when the command field contains text
- shows a **V-SPACE understood** card before confirmation
- displays interpreted date/mode/intensity/time constraints/focus requests
- shows assumptions explicitly so the user can review them
- visually distinguishes prompt-derived unavailable time
- visually distinguishes requested focus blocks
- keeps the existing preview -> prepare -> confirm safety flow

## Examples expected to work

- `Tomorrow I have university until 2 PM, then I want 3 hours for V-SPACE and 90 minutes for calculus.`
- `Plan my week around my classes and make sure I finish deployment before Friday.`
- `I'm tired today, give me a lighter plan and move the hard tasks to tomorrow.`
- `I have an exam on Monday, spread revision across the next 4 days.`
- `I missed the morning. Replan the rest of today.`

## Database
No schema change is required for Stage 3.

Expected Alembic head remains:

`20260911_0002`

Do **not** add or run a new Stage 3 migration.

## Validation completed in the patch environment

- Python syntax/compile: PASS
- deterministic language parser smoke examples: PASS
- TSX transpile/syntax: PASS
- CSS contract: PASS
- unsafe HTML/eval/exec source scan: PASS

Full Flask pytest is not runnable in the patch sandbox because Flask is not installed there. Run the commands below in the normal project environment.

## Run after applying

From `backend`:

```powershell
py -3.11 -m pytest -q tests/test_smart_planner_v1.py tests/test_smart_planner_v1_stage2.py tests/test_smart_planner_v1_stage3.py
py -3.11 -m pytest -q
py -3.11 -m alembic -c migrations/alembic.ini current
```

Expected current revision:

`20260911_0002 (head)`

From `frontend`:

```powershell
npm run build
npm run css:check
```

## Files in this patch

- `backend/services/smart_planner_language_service.py`
- `backend/services/smart_planner_service.py`
- `backend/lifeos/api/v1/planner.py`
- `backend/tests/test_smart_planner_v1_stage3.py`
- `frontend/src/pages/SmartPlannerPage.tsx`
- `frontend/src/styles/smart-planner.css`

## Remaining Smart Planner V1 polish after Stage 3

If acceptance tests pass, Smart Planner is functionally V1-complete. Remaining work should be product polish rather than a new architecture layer: planner onboarding, drag/resize interaction if desired, better mobile timeline ergonomics, and later Private Tutor -> Smart Planner study recommendations.
