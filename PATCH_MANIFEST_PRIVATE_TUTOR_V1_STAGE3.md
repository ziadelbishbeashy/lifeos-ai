# V-SPACE AI — Private Tutor V1 Stage 3

## Purpose
Stage 3 turns Private Tutor from a manually configured grounded study helper into a **course-aware, personalized tutor**.

A user can now type a natural request such as:

> I want to study Calculus

V-SPACE deterministically matches that request to an owned course workspace, shows what it knows about that course, and personalizes the next study session from trusted course material plus deterministic learning history.

## Important: cumulative patch
This Stage 3 patch is **cumulative from Private Tutor V1**. It includes the Stage 2 conversation/mastery changes as well as Stage 3, so you do **not** need to apply the separate Stage 2 ZIP first.

Baseline expected before applying:
- Private Tutor V1 is already present.
- Alembic current/head before this cumulative patch: `20260911_0003`.

After applying and migrating:
- Alembic head: `20260912_0001`.

There is **no additional Stage 3 schema migration**. Stage 3 reuses the Stage 2 mastery/session schema.

## Stage 3 behavior

### 1. Natural course discovery
New read-only endpoint:
- `POST /api/v1/tutor/resolve-study`

The resolver uses owned module metadata only. It does not call an LLM and never exposes another user's courses.

Results:
- `matched` — one course is confidently selected.
- `ambiguous` — multiple owned courses could match; user must choose.
- `no_match` — Private Tutor does not pretend to have course expertise.

Example:
- `I want to study Calculus` -> owned `Calculus` module.

If no course matches, the UI clearly offers:
- general Ask V-SPACE (general model knowledge), or
- creating/selecting a course workspace.

### 2. Course expertise profile
New read-only endpoint:
- `GET /api/v1/tutor/modules/<module_id>/profile`

The profile summarizes:
- grounded document count
- lecture count
- previous Tutor sessions
- graded quiz count
- tracked mastery topics
- weighted overall mastery
- weakest/strongest topics
- study streak
- active study days over the last 30 days
- latest Tutor session
- nearest upcoming assessment
- deterministic next-study recommendation

Expertise states are explicit:
- `course_workspace` — module exists but has no grounded study material yet.
- `course_expert` — course material is available.
- `personalized_course_expert` — course material plus Tutor/mastery history are available.

### 3. Adaptive difficulty
Tutor difficulty now supports:
- Adaptive
- Beginner
- Intermediate
- Advanced

Adaptive mode is deterministic:
- mastery < 45% -> Beginner
- mastery 45–79% -> Intermediate
- mastery >= 80% -> Advanced
- no mastery baseline -> Intermediate

Topic-specific mastery is preferred when the user names a known topic; otherwise weighted course mastery is used.

### 4. Weak-topic-first tutoring
For broad requests such as:
- `I want to study Calculus`
- `Quiz me`
- `Help me study`

Private Tutor now uses tracked weak topics to guide retrieval and question emphasis instead of repeatedly teaching random/general material.

Course facts remain grounded only in the existing Document Brain evidence. Mastery/history is used only to adapt pedagogy, difficulty and emphasis.

### 5. Course-aware home UI
Private Tutor now shows:
- natural-language “What do you want to study?” entry
- automatic course match
- explicit Course Expert / Personalized Course Expert badge
- course knowledge stats
- mastery summary
- weak topics
- study streak
- upcoming assessment
- recommended next study action
- Continue where I stopped
- Adaptive difficulty control

### 6. Stage 2 retained and improved
The cumulative patch also includes:
- persistent Tutor conversation threads
- deterministic mastery tracking
- repeated quiz progress
- Review mistakes
- Quiz again
- Tutor -> Smart Planner revision handoff

Stage 3 also fixes conversation continuity: prior Tutor context is now actually supplied to follow-up/retry generations while remaining explicitly non-authoritative for course facts.

## Architecture / trust rules preserved
Private Tutor still uses:

`Module -> Document Brain retrieval -> existing provider router -> validated Tutor response`

No duplicate RAG stack was added.

- Course documents remain the factual authority.
- Tutor history/mastery never becomes factual evidence.
- Natural course resolution is deterministic and ownership-scoped.
- AI never writes directly to Smart Planner or other workspace tables.
- Planner handoff still goes through the existing Smart Planner preview/confirmation flow.
- Quiz answer keys remain server-side until grading.

## Files in this cumulative patch
- `backend/models.py`
- `backend/migrations/versions/20260912_0001_private_tutor_stage2.py`
- `backend/services/private_tutor_service.py`
- `backend/services/private_tutor_personalization_service.py` (new)
- `backend/lifeos/api/v1/tutor.py`
- `backend/tests/test_private_tutor_v1_stage2.py`
- `backend/tests/test_private_tutor_v1_stage3.py` (new)
- `frontend/src/pages/PrivateTutorPage.tsx`
- `frontend/src/styles/private-tutor.css`

## Validation commands
Backend:

```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\backend
py -3.11 -m pytest -q tests/test_private_tutor_v1.py tests/test_private_tutor_v1_stage2.py tests/test_private_tutor_v1_stage3.py
py -3.11 -m pytest -q
py -3.11 -m alembic -c migrations/alembic.ini upgrade head
py -3.11 -m alembic -c migrations/alembic.ini current
```

Expected Alembic head:

```text
20260912_0001 (head)
```

Frontend:

```powershell
cd ..\frontend
npm run build
npm run css:check
```

## Suggested smoke test
1. Create/select a module named `Calculus` with at least one searchable document.
2. Open Private Tutor.
3. Enter `I want to study Calculus` in the natural study box.
4. Confirm it resolves to the Calculus workspace and shows `Course expert` or `Personalized course expert`.
5. Start an Adaptive quiz.
6. Grade the quiz with at least one wrong answer.
7. Return to the Tutor home/profile and confirm weak-topic mastery appears.
8. Enter `I want to study Calculus` again and confirm V-SPACE recommends/targets the weak area.
9. Use Review mistakes, Quiz again, and Plan revision.
