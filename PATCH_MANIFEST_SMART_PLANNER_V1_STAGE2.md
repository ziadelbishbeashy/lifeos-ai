# V-SPACE AI — Smart Planner V1 Stage 2

Apply this patch **after** `v-space-ai-smart-planner-v1-stage1`.

## Product goal
Stage 2 turns the accepted Smart Planner schedule into a real daily planning surface while preserving the V-SPACE trust boundary:

- exact time arithmetic remains deterministic;
- fixed commitments are treated as unavailable time;
- manual UI edits are explicit deterministic user actions;
- V-SPACE-generated and rebalanced schedules remain preview-only until I9 confirmation;
- no LLM writes schedule rows directly.

## Added

### Fixed commitments
- New `smart_planner_commitments` table.
- Add/remove explicit classes, meetings, exams, appointments, personal events or other fixed time.
- Planner schedules around overlapping fixed time instead of over it.
- Academic integration: timed `ModuleAssessment` items are exposed automatically as read-only academic commitments.

### Accepted-plan editing
- Edit an accepted task block's date/start/end.
- Collision checks against other task blocks and fixed commitments.
- Lock/unlock a task block.
- Locked blocks are preserved by subsequent rebalance previews.
- Completed task blocks remain historical and are not manually moved.

### Rebalance remaining
- Accepted plans can generate a read-only rebalance preview from today (or a selected remaining date).
- Completed work is excluded from rescheduling.
- Locked future blocks remain fixed.
- Rebalance still uses the same `apply_smart_plan` I9 proposal + explicit confirmation boundary.
- Accepted replacement plans record `supersedes_plan_id`.

### Goal plan foundation
- New `goal` mode with a configurable 2–14 day horizon.
- Goal text is required and is used by the existing deterministic request-match ranking bonus.
- This stage plans existing trusted tasks; AI task decomposition remains a later intelligence enhancement.

### Live plan state
Saved blocks now expose:
- `completed`
- `missed`
- `current`
- `upcoming`

Task completion is reflected from the authoritative Task row; planner blocks do not duplicate completion state.

### UI
- Day / Week / Goal modes.
- Four-part capacity summary: plan range, scheduled work, fixed time, workload fit.
- Fixed commitments displayed directly in the timeline.
- Fixed commitment manager in the sidebar.
- Academic commitments visually marked read-only.
- Manual block editor with lock toggle.
- Rebalance remaining action on accepted plans.
- Clear preview vs accepted vs rebalanced states.
- Responsive and dark-theme additions.

## Schema
New Alembic head:

`20260911_0002`

Migration:

`backend/migrations/versions/20260911_0002_smart_planner_stage2.py`

It adds:
- `smart_planner_commitments`
- `smart_planner_plans.project_id`
- `smart_planner_plans.supersedes_plan_id`

## Files
- `backend/models.py`
- `backend/services/smart_planner_service.py`
- `backend/lifeos/api/v1/planner.py`
- `backend/migrations/versions/20260911_0002_smart_planner_stage2.py`
- `backend/tests/test_smart_planner_v1_stage2.py`
- `frontend/src/pages/SmartPlannerPage.tsx`
- `frontend/src/styles/smart-planner.css`

## Validation completed in the patch environment
- Python `py_compile` / `compileall`: PASS
- Smart Planner TSX transpile/syntax check with TypeScript: PASS
- `npm run css:check`: PASS
- unsafe `dangerouslySetInnerHTML` / Python `eval` / `exec` source scan on modified planner files: PASS

Full pytest could not run in this sandbox because Flask is not installed (`ModuleNotFoundError: flask`). Run the commands below in the normal LifeOS/V-SPACE environment.

## Run after applying

```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\backend

py -3.11 -m pytest -q tests/test_smart_planner_v1.py tests/test_smart_planner_v1_stage2.py
py -3.11 -m pytest -q

flask db upgrade
flask db current
```

Expected Alembic head:

`20260911_0002`

Then:

```powershell
cd ..\frontend
npm run build
npm run css:check
```

## Suggested manual acceptance
1. Add a 09:00–11:00 class, build a day plan, verify no task overlaps it.
2. Add a timed module assessment and verify it appears automatically as an academic fixed commitment.
3. Accept a plan, edit one task to 14:00–15:00, lock it, then rebalance; verify it stays at 14:00.
4. Mark a planned task Completed in Tasks; verify its planner block becomes Done.
5. Let a block pass without completion; verify it shows Missed.
6. Create a Goal plan for 5–10 days and verify it uses only the selected horizon.
7. Rebalance an accepted schedule; verify no accepted plan is replaced before I9 confirmation.

## Deliberately not included yet
- Natural-language parsing of ad-hoc commitments from the planner prompt.
- AI decomposition of a new goal into brand-new tasks.
- Drag/drop gestures; Stage 2 uses a deterministic edit panel first.
- Recurring commitment rules.
- Calendar-provider sync.
- Private Tutor study-performance feedback into planner recommendations.

Those belong in Smart Planner Stage 3 / Private Tutor integration after Stage 2 is validated.
