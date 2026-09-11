# I17 — Intelligence Automations V1

## Product goal

I17 automates **repeated intelligence work**, not the basic deadline emails LifeOS already has.

The engine can automatically prepare:

1. Morning intelligence briefing — current priorities, deadlines, document attention, study state, and recent changes.
2. Weekly intelligence review — project review plus meaningful changes from the current week.
3. Project risk escalation — only when several trusted signals combine into a broader project risk.
4. Unhandled document follow-up — current document risks/actions that still have no confirmed task/note provenance.
5. Optional event-context rules — enrich an allow-listed I14 event with its owned project context.

## Safety boundary

Automation execution may write only:

- `lifeos_automation_runs` audit rows;
- normalized `LifeOSIntelligenceEvent` delivery metadata;
- I15 proactive notification metadata.

It may **not** directly create/update/delete Projects, Tasks, Notes, Documents, Modules, Lectures, or Collections. Any future workspace-changing action still goes through I9 confirmation.

No arbitrary code, SQL, URLs, provider prompts, or user-defined event names are executable.

## Delivery flow

```text
Schedule / I14 event
        ↓
I17 candidate matcher
        ↓
Allow-listed read-only intelligence action
        ↓
Automation run audit
        ↓
I14 automation-result event
        ↓
I15 in-app notification
        ↓
User decides what to do
        ↓
I9 confirmation for any workspace change
```

## Runtime

Manual `Run now` works from the Automations page/API without the background worker.

Background schedules/event rules require the separate worker process and the explicit environment gate:

```env
ENABLE_LIFEOS_AUTOMATIONS=true
LIFEOS_AUTOMATION_POLL_SECONDS=60
```

Windows/local development:

```powershell
cd backend
$env:ENABLE_LIFEOS_AUTOMATIONS="true"
python -m workers.automation_worker
```

Docker Compose includes a dedicated `automation-worker` service.

V1 assumes **one automation worker process**. Multi-worker claiming/leases belong to a later production-hardening pass if horizontal worker scaling is introduced.

## Useful CLI checks

```powershell
python -m flask --app app automation-registry
python -m flask --app app automation-list --user-id 1
python -m flask --app app automation-candidates --user-id 1
python -m flask --app app automation-run --user-id 1 --automation-id 1
python -m flask --app app automation-run-due --user-id 1
```

## No migration change from preparation

I17 activation reuses the already-installed preparation schema. The migration head remains:

```text
20260830_0001
```
