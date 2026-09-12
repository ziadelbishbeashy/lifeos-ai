# V-SPACE Personalization V2 + Smart Planner Intelligence

## Purpose
This patch addresses the first-use personalization and Smart Planner issues found during manual testing:

- First-time personalization felt like a technical settings form.
- Several questions were unclear to users who do not yet know how Smart Planner works.
- Saved personalization did not materially constrain normal planner workload enough.
- User-facing planner/profile time used 24-hour values in several places.
- Conversational phrases such as “10 in the morning” and “10 at night” needed deterministic understanding.
- Ambiguous point times needed clarification rather than risky silent guessing.
- Users could not clearly see *why* a saved profile changed a plan.

## User experience changes

### 7-step onboarding
The first-login profile is now a short guided conversation:
1. What V-SPACE should help manage.
2. Normal wake/sleep routine.
3. Regular commitments.
4. Best concentration period.
5. Focus-session and break rhythm.
6. How full a normal plan should feel.
7. What to do when the day is overloaded, plus optional advanced boundaries.

Every step explains what the answer changes. All questions remain optional and editable later.

### AM/PM UI
A reusable `TimePicker12h` component displays and accepts 12-hour time while APIs/database values remain deterministic `HH:MM` internally.

Applied to:
- Personalization
- Smart Planner
- Dashboard schedule preview
- Task reminders
- Academic schedule import
- Module assessments
- Notification schedule/quiet hours

### Natural-language time understanding
The deterministic planner parser now understands examples including:
- `10 AM`
- `10 in the morning`
- `10 at the morning`
- `2 in the afternoon`
- `7 in the evening`
- `10 at night`
- `noon`
- `midnight`

A risky phrase such as `gym at 10` asks AM/PM when there is no reliable context. If a matching saved routine exists, its AM/PM tendency and normal duration may be used, and the assumption is disclosed.

## Stronger profile -> planner behavior
Saved profile data now influences deterministic scheduling through:
- wake/sleep-derived usable boundaries
- explicit focused-work boundaries
- avoid-after boundary
- productive-period preferred placement
- focus-block length
- break length
- planning-capacity factor / breathing room
- regular recurring commitments
- small deterministic task-ranking preference for selected priorities
- overload behavior

Priority remains:
`current request > explicit/manual/academic commitments > profile > V-SPACE defaults`

Explicit focus durations in the current request remain higher priority than profile capacity preferences.

## Trust / explanation
Planner previews can show:
- `This plan used your V-SPACE Profile`
- `Why V-SPACE planned it this way`
- specific reasons such as sleep boundary, evening focus preference, saved gym routine, focus length, breaks, or intentional breathing room.

Ambiguous time input is surfaced as a friendly “One quick detail” clarification instead of creating a misleading plan.

## Database
No migration is required. This patch reuses the existing `user_personalization_profiles` schema.

Expected Alembic head remains whatever current Authentication V1 head is already installed (normally `20260912_0003`).

## Validation performed in build workspace
- Python compilation passed for changed backend services/tests.
- Deterministic parser smoke tests passed for morning/afternoon/evening/night/noon/midnight and ambiguity handling.
- TypeScript/TSX transpilation passed for all changed frontend files.
- CSS contract passed.
- Changed-path static scan found no dangerous HTML injection or command-execution additions.
- Full Flask pytest could not run in the build container because Flask is not installed there; run the commands below locally.

## Local validation
```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\backend
py -3.11 -m pytest -q tests/test_personalization_profile_v1.py tests/test_smart_planner_v1.py tests/test_smart_planner_v1_stage2.py tests/test_smart_planner_v1_stage3.py
py -3.11 -m pytest -q

cd ..\frontend
npm run build
npm run css:check
```

## Manual scenarios
1. Complete the new seven-step profile with wake 8 AM, sleep 1 AM, evening focus, 60-minute focus blocks, 15–20 minute breaks, a balanced plan, and a recurring gym routine.
2. Ask: `Plan tomorrow. I need to work on V-SPACE and study calculus.` Confirm that the saved routine and peak focus visibly influence the result.
3. Ask: `Tomorrow I have university until 2 in the afternoon and gym at 10 at night.` Confirm 2:00 PM and 10:00 PM.
4. Without a matching saved routine, ask: `Tomorrow I have gym at 10.` Confirm that V-SPACE asks whether that means 10:00 AM or 10:00 PM.
5. With a saved evening gym routine, ask the same phrase and confirm the interpretation is disclosed and uses the saved routine duration unless explicitly overridden.
