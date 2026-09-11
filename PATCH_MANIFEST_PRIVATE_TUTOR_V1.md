# V-SPACE AI — Private Tutor V1

## Baseline
Built against the user-provided `lifeos-ai-feature-hybrid-rag (18).zip`, which already contains the redesigned V-SPACE frontend and Smart Planner V1 Stages 1–3.

## Product scope delivered
Private Tutor is now a dedicated V-SPACE learning experience rather than a thin Ask V-SPACE prompt mode.

### Study setup
- Select an owned Learning Module.
- Optionally narrow to a Lecture.
- Choose Beginner / Intermediate / Advanced depth.
- Supply an optional topic and learning request.
- Uses only current documents already linked to that module/lecture scope.

### Modes
1. Explain — grounded explanation, key points, self-check questions.
2. Summarize — grounded exam/revision summary and key points.
3. Quiz me — interactive multiple-choice quiz.
4. Practice — guided questions, hints, and worked solutions.
5. Flashcards — active-recall cards with flip interaction.

### Grounding and trust
- Reuses the authoritative Module -> Document Brain hybrid retrieval pipeline.
- No duplicate RAG/vector/retrieval implementation.
- Ownership is checked through existing module/lecture ownership services.
- Retrieved document content stays inside the existing prompt-injection security boundary.
- AI output is requested in provider-native JSON mode and validated before persistence/display.
- Every generated learning item must cite one of the supplied retrieved Source IDs.
- Sources are shown in the UI with document/page/section evidence.

### Quiz behavior
- Correct answers are stored server-side and are not returned in the initial quiz payload.
- Grading is deterministic server-side code, not an LLM judgment.
- Shows score, explanations, correct answer review, and weak topics.
- Saves score/weak-area history to the user-owned tutor session.

### Smart Planner bridge
After a graded quiz has weak areas, `Plan revision` opens Smart Planner with a pre-filled natural-language request such as:
`Schedule 45 minutes to revise <weak areas> for <module>.`
Smart Planner still handles preview/proposal/confirmation using its existing safety architecture.

## Database
New table: `private_tutor_sessions`

Stores user-owned tutor generation history, structured study payload, source evidence references, quiz answers, score, and weak areas.

New Alembic revision:
- `20260911_0003_private_tutor_v1.py`
- revision: `20260911_0003`
- down revision: `20260911_0002`

Expected Alembic head after applying this patch: `20260911_0003`.

## API
New API boundary: `/api/v1/tutor`

- `GET /api/v1/tutor`
- `POST /api/v1/tutor/sessions`
- `GET /api/v1/tutor/sessions/<id>`
- `POST /api/v1/tutor/sessions/<id>/grade`

## Frontend
New dedicated page:
- `frontend/src/pages/PrivateTutorPage.tsx`

New styling:
- `frontend/src/styles/private-tutor.css`

The page uses the redesigned dark-blue V-SPACE token system and existing application shell.

## Validation performed in this environment
Passed:
- Python compilation for changed backend Python files.
- Alembic revision discovery: `20260911_0003 (head)`.
- Frontend CSS contract: PASS.
- TSX syntax/transpile validation for PrivateTutorPage, SmartPlannerPage, and App.
- Static scan: no `dangerouslySetInnerHTML`, `eval`, or `exec` introduced in Tutor code.

Not runnable here:
- Full pytest / targeted pytest: sandbox Python environment does not have Flask installed (`ModuleNotFoundError: flask`).
- Full `npm run build`: uploaded project does not include `node_modules`; use the user's normal frontend environment.

## Recommended local validation
From `backend`:

```powershell
py -3.11 -m pytest -q tests/test_private_tutor_v1.py
py -3.11 -m pytest -q
py -3.11 -m alembic -c migrations/alembic.ini upgrade head
py -3.11 -m alembic -c migrations/alembic.ini current
```

Expected current revision:

```text
20260911_0003 (head)
```

From `frontend`:

```powershell
npm run build
npm run css:check
```

## Deliberately deferred to the next Tutor iteration
- Persistent multi-turn Tutor conversation threads.
- Long-term mastery analytics across repeated quizzes.
- Spaced-repetition scheduling logic.
- Direct Tutor-created Smart Planner proposal (current V1 safely hands a natural-language request to Planner instead).
- Direct single-document tutor scope outside Modules; Ask V-SPACE remains available for arbitrary document Q&A.
