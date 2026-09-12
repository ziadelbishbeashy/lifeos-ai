# V-SPACE AI — Private Tutor V1 Stage 2

Apply this patch over the current V-SPACE project after Private Tutor V1.

## Scope
Stage 2 extends the existing Private Tutor without creating another intelligence or RAG stack.

### Added
- Persistent tutor conversation threads.
- Grounded follow-up questions that retain module/lecture scope.
- Deterministic per-topic mastery tracking from graded quizzes.
- Repeated-quiz progress and best/latest mastery metrics.
- "Review mistakes" flow that creates a new grounded tutor explanation from weak areas.
- "Quiz again" flow that creates a fresh quiz in the same conversation and emphasizes prior weak areas.
- Better historical quiz review: graded sessions serialize deterministic answer review data.
- Stronger Tutor → Smart Planner handoff using score-based revision duration and weak topics.
- Private Tutor UI for mastery bars, recent quiz trend, conversation navigation, post-quiz actions, and follow-up composer.

## Architecture preserved
- One V-SPACE intelligence core.
- Existing Module → Document Brain retrieval remains authoritative.
- No duplicate embeddings or RAG pipeline.
- Quiz grading and mastery math are deterministic server-side.
- Tutor never directly mutates Smart Planner state; it passes a planning prompt to the existing Planner preview/confirmation flow.
- Existing ownership checks remain in place.

## Database
New migration:
- `20260912_0001_private_tutor_stage2.py`
- Revises: `20260911_0003`
- New expected Alembic head: `20260912_0001`

Changes:
- `private_tutor_sessions.conversation_key`
- `private_tutor_sessions.parent_session_id`
- new `private_tutor_mastery` table

## Main files
- `backend/models.py`
- `backend/services/private_tutor_service.py`
- `backend/lifeos/api/v1/tutor.py`
- `backend/migrations/versions/20260912_0001_private_tutor_stage2.py`
- `backend/tests/test_private_tutor_v1_stage2.py`
- `frontend/src/pages/PrivateTutorPage.tsx`
- `frontend/src/styles/private-tutor.css`

## Validation performed here
Passed:
- Python compile for changed backend/migration/test files.
- CSS contract check.
- Security source scan for `dangerouslySetInnerHTML`, `eval`, and `exec` in changed Tutor paths.

Environment limitations:
- Full pytest could not run in this sandbox because Flask is not installed.
- Full frontend build could not run because the sandbox lacks the project's React/Vite node_modules.

## Run locally
Backend:
```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\backend
py -3.11 -m pytest -q tests/test_private_tutor_v1.py tests/test_private_tutor_v1_stage2.py
py -3.11 -m pytest -q
py -3.11 -m alembic -c migrations/alembic.ini upgrade head
py -3.11 -m alembic -c migrations/alembic.ini current
```
Expected head:
```text
20260912_0001 (head)
```

Frontend:
```powershell
cd ..\frontend
npm run build
npm run css:check
```
