# LifeOS Intelligence I9 + I10

## Trust contract

1. Agent output may recommend an action; it cannot execute one.
2. Creating an Action Proposal changes no user workspace resource.
3. Every proposal requires a second authenticated confirmation.
4. Confirmation re-checks ownership and the action allow-list.
5. The existing Task/Note/Document services perform the real write.
6. Duplicate confirmations fail closed.
7. Meaningful confirmed changes are auditable through I10.
8. Activity records contain metadata/state changes, never hidden prompts or secrets.

## Local verification

```powershell
cd backend
python -m flask --app app db current
python -m flask --app app db heads
python -m flask --app app db upgrade
python -m flask --app app db current

python -m pytest tests -k "i9 or i10 or intelligence or project_review" -v
python -m pytest tests -q

python -m flask --app app intelligence-activity `
  --user-id 1 `
  --query "What changed this week?"
```

Expected migration head: `20260829_0001 (head)`.

Frontend:

```powershell
cd ..\frontend
npm run build
```

Manual acceptance:

1. Ask: `Review my project and tell me what needs attention`.
2. Choose a priority with `Create task`, `Save note`, or `Refresh analysis`.
3. Verify the first click shows a confirmation card and no resource exists yet.
4. Confirm the action and verify exactly one resource/change occurs.
5. Ask: `What changed in LifeOS this week?`.
6. Verify the confirmed change appears in the recent timeline.
7. Verify another user's proposal/activity cannot be accessed by ID.
