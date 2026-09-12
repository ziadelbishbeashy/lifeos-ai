# V-SPACE Personalization / Life Context V1

## Purpose
Adds an optional privacy-first V-SPACE Profile that learns a user's routine and planning preferences without making the product dependent on onboarding completion.

## Product behavior
- First authenticated private screen shows a one-time personalization prompt when no profile exists.
- User can choose **Start personalization** or **Maybe later**.
- Choosing Maybe later records only the deferred state; it does not invent answers.
- Deferred users are not blocked and are not prompted on every login.
- Dashboard keeps a lightweight reminder linking to Settings.
- Settings → Personalization exposes the full profile, field-by-field data-use information, edit controls and **Clear personalization**.
- Every question is optional.

## 12 profile questions
1. Usual wake time
2. Usual sleep time
3. Most productive period
4. Preferred focus-session length
5. Preferred break length
6. Planning intensity
7. Default focused-work start
8. Default focused-work end
9. Avoid scheduling after
10. Regular recurring commitments
11. Current priorities
12. Overload behavior

## Privacy boundary
- Profile data is owned by exactly one authenticated user.
- The session payload exposes only onboarding/configuration summary, not the full life-context values.
- Full values are available only from the authenticated personalization endpoint.
- V1 uses life-context directly in deterministic product logic and does **not** send the profile to web-search providers.
- The profile is not automatically injected into every AI request.
- User can edit or clear the optional profile at any time.
- No medical/health-condition fields are collected.

## Smart Planner integration
Smart Planner now uses relevant profile preferences when the user did not explicitly override them:
- focused-work start/end
- avoid-after time
- productive period as a soft default window when direct work hours are absent
- wake/sleep as soft schedule guardrails when direct work hours are absent
- preferred break length
- planning intensity (light / balanced / productive / intense)
- recurring commitments as read-only profile commitments
- overload preference to explain how excess work is handled

Priority order remains:
1. explicit current planning request / controls
2. persisted manual and academic commitments
3. V-SPACE Profile preferences and routines
4. visible safe V-SPACE defaults

Natural-language commitments with the same title/date override matching profile routines in that preview, so `gym at 8 PM` does not duplicate a saved `Gym 7–8:30 PM` routine.

## New API
- `GET /api/v1/personalization`
- `PATCH /api/v1/personalization`
- `POST /api/v1/personalization/defer`
- `DELETE /api/v1/personalization`

## Database
New table: `user_personalization_profiles`

Migration:
- `20260912_0002_personalization_life_context.py`
- revision: `20260912_0002`
- down revision: `20260912_0001`

Expected Alembic head after upgrade:
`20260912_0002`

## Changed files
- `backend/models.py`
- `backend/services/personalization_profile_service.py`
- `backend/services/smart_planner_service.py`
- `backend/lifeos/api/v1/personalization.py`
- `backend/lifeos/api/v1/__init__.py`
- `backend/lifeos/api/v1/routes.py`
- `backend/migrations/versions/20260912_0002_personalization_life_context.py`
- `backend/tests/test_personalization_profile_v1.py`
- `frontend/src/api/types.ts`
- `frontend/src/components/PersonalizationProfile.tsx`
- `frontend/src/App.tsx`
- `frontend/src/native/NativeWorkspaceShell.tsx`
- `frontend/src/pages/DashboardPage.tsx`
- `frontend/src/pages/ExperienceSettingsPage.tsx`
- `frontend/src/pages/SmartPlannerPage.tsx`
- `frontend/src/styles/app.css`
- `frontend/src/styles/personalization.css`
- `frontend/scripts/check-css-contract.mjs`

## Validation performed in build environment
Passed:
- Python `py_compile` for all changed backend Python files.
- TypeScript/TSX syntax transpilation for changed frontend files.
- CSS contract check.
- Alembic graph static check: single head `20260912_0002` and parent `20260912_0001` present in reconstructed baseline.
- Static changed-path scan found no `dangerouslySetInnerHTML`, `eval`, or `exec` additions.

Not run here:
- Full Flask pytest suite, because Flask is not installed in this build environment.
- Full Vite build, because project node_modules are not installed in this build environment.

## Suggested local verification
```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\backend
py -3.11 -m pytest -q tests/test_personalization_profile_v1.py tests/test_smart_planner_v1.py tests/test_smart_planner_v1_stage2.py tests/test_smart_planner_v1_stage3.py
py -3.11 -m pytest -q
py -3.11 -m alembic -c migrations/alembic.ini upgrade head
py -3.11 -m alembic -c migrations/alembic.ini current
```
Expected: `20260912_0002 (head)`.

Frontend:
```powershell
cd ..\frontend
npm run build
npm run css:check
```
