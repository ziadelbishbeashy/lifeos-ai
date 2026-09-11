# LifeOS Ask LifeOS Reasoning + I9 Security Upgrade

Baseline: latest full project ZIP supplied by the user (`lifeos-ai-feature-hybrid-rag (14).zip`).

## Product behavior

- Adds `project_advice` as a distinct Ask LifeOS intent.
- Exact project facts remain deterministic (`project_question`).
- Project advice uses trusted LifeOS context as factual grounding while allowing model/domain expertise for solutions, alternatives, trade-offs, debugging strategies, architecture advice, and prioritization.
- Project review reasoning is also instructed to add useful analysis instead of merely paraphrasing fields.
- Recommendations no longer have to already exist in LifeOS facts; workspace inferences still require trusted support.
- The independent verifier remains strict on workspace facts and execution claims while explicitly permitting outside/domain knowledge for clearly advisory content.
- Generic `help me ...` wording no longer automatically triggers I19. Clear multi-step goals such as deployment/launch/finish/blocker goals still use the existing LangGraph/I19 path.
- Model Router gains `ask_lifeos_advisor` at the NORMAL tier and respects the existing Fast/Balanced/Deep user override policy.

## I9 hardening

- Ask LifeOS/Home priorities shown to the browser receive a short-lived HMAC authorization envelope bound to:
  - authenticated user
  - project
  - priority contents/evidence
  - issue time
- `/api/v1/intelligence/action-proposals` now requires that signed priority envelope.
- Tampering with title/reason/recommendation/evidence/project invalidates proposal preparation.
- Server-internal verified agent proposal preparation remains server-side and does not depend on a client token.
- Confirmation now rechecks that the action type is allow-listed and `requires_confirmation` is true before execution.
- No AI path writes directly to the database; existing deterministic services remain the only action executors.

## Database

No migration. Expected Alembic head remains `20260906_0001`.

## Local verification

Backend:

```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\backend
py -3.11 -m pytest tests\test_ask_lifeos_reasoning_i9_upgrade.py -q
py -3.11 -m pytest tests\test_intelligence_reasoning_i4_i5.py -q
py -3.11 -m pytest tests\test_intelligence_actions_activity_i9_i10.py -q
py -3.11 -m pytest tests\test_agentic_ask_lifeos_i19.py -q
py -3.11 -m pytest tests\test_ai_model_router.py -q
py -3.11 -m pytest -q
```

Frontend:

```powershell
cd ..\frontend
npm run build
npm run css:check
```

## Manual quality checks

With a Project selected in Ask LifeOS:

1. `What is my project progress?`
   - should remain deterministic and exact.
2. `How can I simplify this project and finish faster?`
   - should produce real recommendations/strategy, not just restate tasks.
3. `What would you change about this architecture?`
   - should use domain expertise while keeping LifeOS facts exact.
4. `Help me simplify this architecture.`
   - should answer directly rather than automatically preparing an I19 plan.
5. `Help me get this project ready for deployment.`
   - should still use the existing I19/LangGraph goal flow.
6. From a Home/Ask priority, click Create task/Save note:
   - proposal should be pending first;
   - workspace remains unchanged until Confirm;
   - confirmed action executes once.

LangSmith should show `ask_lifeos_advisor` for the new advisory generation call.
