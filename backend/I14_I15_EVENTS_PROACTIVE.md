# I14 + I15 — Event Engine and Proactive Intelligence

## What I14 does

I14 converts trusted LifeOS state and the existing I10 activity log into one
normalized event stream. V1 detects current conditions such as overdue/blocked
work, deadlines within three days, project deadlines, stale/missing document
analysis, plus recent mutation events such as document version changes,
completed analysis, task changes, notes, projects, and confirmed intelligence
actions.

The event engine is deterministic, ownership-bounded, idempotent and does not
call an LLM. State conditions are resolved automatically when they stop being
true.

## What I15 does

I15 consumes I14 and surfaces attention-worthy events without waiting for an
Ask LifeOS question. V1 delivery is **in-app**:

- the top-bar bell shows an unread badge;
- LifeOS refreshes proactive intelligence every 60 seconds while the app is open;
- `/notifications/history` shows verified proactive notices;
- users can open the related resource, mark a notice read, dismiss it, or mark
  all read.

I15 does **not** execute tasks, notes, refreshes, emails, or other workspace
changes. Any future action still goes through the I9 proposal + explicit user
confirmation contract.

## V1 trigger → notice examples

- `task.overdue` → high-attention in-app notice
- `task.blocked` → high-attention in-app notice
- `deadline.approaching` → upcoming task notice
- `project.overdue` / `project.deadline_approaching` → project attention notice
- `document.intelligence_stale` → open the document before trusting old analysis
- `document.analysis_completed` → analysis-ready informational notice

Other normalized events remain available to later automations even if I15 does
not notify on them, preventing notification spam.

## CLI verification

```powershell
python -m flask --app app intelligence-events --user-id 1
python -m flask --app app intelligence-proactive --user-id 1
```

## Migration

`20260829_0003` adds only:

- `lifeos_intelligence_events`
- `lifeos_proactive_notifications`

No existing project/task/document schema is altered.
