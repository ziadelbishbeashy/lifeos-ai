> Historical preparation checkpoint. I17 is now activated; see `I17_AUTOMATIONS_V1.md` for the current execution and safety contract.

# I17 — Automations V1 Preparation

## Goal

Prepare every contract needed for safe LifeOS automations before background execution is enabled.

I17 preparation is intentionally **non-autonomous**. Users can define, validate, enable/disable, and preview rules, but no worker may execute an automation action yet.

## Architecture prepared

```text
Schedule / I14 event
        ↓
LifeOSAutomation definition
        ↓
Trigger validation + owner isolation
        ↓
Candidate evaluation
        ↓
Reviewed action adapter
        ↓
PREPARATION GATE (execution disabled)
        ↓
Future I17 activation
        ↓
I15 notification / generated review
        ↓
I9 confirmation for workspace mutation
```

## New tables

- `lifeos_automations`
- `lifeos_automation_runs`

Migration head: `20260830_0001`

The migration adds tables only. Existing Project, Task, Note, Document, Module, Collection, RAG, and intelligence tables are not altered.

## Trigger allow-list

### Scheduled

- `schedule_daily`
- `schedule_weekly`

Schedules store an explicit IANA timezone and precompute `next_run_at` in UTC. `tzdata` is included in backend requirements so Windows can resolve IANA timezone names.

### I14 event-driven

- `task.overdue`
- `task.blocked`
- `deadline.approaching`
- `project.overdue`
- `project.deadline_approaching`
- `document.intelligence_stale`
- `document.version_changed`

No arbitrary webhooks or user-supplied event names are accepted in V1 preparation.

## Action allow-list

- `today_briefing` — deterministic I12 Home/Today packet
- `portfolio_review` — constrained I8 portfolio review agent
- `project_review` — constrained I8 review for one owned project
- `attention_notice` — verified payload from the matching I14 event

No arbitrary Python, shell commands, SQL, URLs, provider prompts, or external API calls are stored or executed.

## API

Authenticated routes:

- `GET /api/v1/automations/registry`
- `GET /api/v1/automations`
- `POST /api/v1/automations`
- `PATCH /api/v1/automations/<id>`
- `DELETE /api/v1/automations/<id>`
- `POST /api/v1/automations/<id>/preview`
- `GET /api/v1/automations/<id>/runs`

## UI

`/automations` is available from the Intelligence navigation.

It includes:

- preparation-mode safety banner;
- starter templates;
- constrained custom builder;
- timezone-aware schedule preparation;
- enable/disable controls;
- read-only preview;
- delete controls;
- clear indication that background execution is not active.

## Worker seam

`python -m workers.automation_worker` now exists, but it is deliberately gated.

Even if `ENABLE_LIFEOS_AUTOMATIONS=true` is set during preparation, the worker can only evaluate candidates. It has **no action executor** and reports `actions_executed=0`.

This prevents accidental autonomy while deployment/process supervision is being prepared.

Configuration prepared:

```env
ENABLE_LIFEOS_AUTOMATIONS=false
LIFEOS_AUTOMATION_POLL_SECONDS=60
LIFEOS_DEFAULT_TIMEZONE=UTC
```

## Activation gate

Do not activate autonomous execution until all of these are green:

1. migration upgraded to `20260830_0001`;
2. I17 preparation tests pass;
3. full backend suite passes;
4. frontend build passes;
5. manual template creation works;
6. preview creates only a run-history row and does not mutate workspace state;
7. owner-isolation test passes;
8. event trigger matches only the user's I14 events;
9. scheduled next-run calculations are confirmed in the user's timezone;
10. execution adapters are reviewed one-by-one before worker activation.

## Safety invariant

Automation intelligence may prepare information automatically. Any future action that changes Tasks, Notes, Documents, Projects, Modules, or other workspace state must still route through the I9 confirmation boundary unless a later, explicitly reviewed policy introduces a narrower safe-action exception.
