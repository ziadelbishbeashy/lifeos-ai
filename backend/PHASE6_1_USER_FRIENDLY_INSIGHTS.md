# LifeOS Phase 6.1 — User-Friendly Note Insights

## What changed

The old note analysis displayed technical categories such as summary, tags, decisions, and questions. The revised workflow is designed around what a user actually needs:

1. **At a Glance** — what the note means and why it matters.
2. **Attention Level** — whether anything needs urgent attention.
3. **Recommended Next Step** — the single best action to take first.
4. **Important Information** — clear facts supported by note evidence.
5. **Decisions and Deadlines** — only when explicitly present.
6. **Risks and Blockers** — what may stop progress.
7. **Missing Information** — useful clarification questions.
8. **Ordered Action Plan** — practical steps with reasons and priorities.
9. **Suggested Workspace Tasks** — users approve or reject each task.
10. **Ask LifeOS** — grounded follow-up questions using the latest analysis.

## Required database step

Before running the revised project against the existing SQL Server database, execute:

```text
sql/phase6_1_ai_notes_complete.sql
```

The script is idempotent. It creates missing Phase 6 tables and adds the new `insights_json` column when required.

## Environment setup

The returned ZIP intentionally does not contain `.env` or Git history. Copy:

```text
.env.example -> .env
```

Then restore your own API keys, database settings, and mail credentials locally.

## Important behavior

- AI never changes the original note.
- Editing a note marks the previous insight as stale.
- Follow-up questions are blocked until the note is analyzed again.
- AI task suggestions are not added automatically.
- Approving a suggestion creates a normal LifeOS task.
- Rejecting a suggestion keeps it out of the workspace.
- Deleting an approved task resets its originating suggestion to Pending.
- Deleting a note removes analyses, questions, and suggestions, but keeps approved real tasks.

## Test checklist

1. Run the SQL migration.
2. Copy `.env.example` to `.env` and restore local secrets.
3. Start the application.
4. Create a Meeting Note containing a decision, deadline, blocker, and action.
5. Analyze the note.
6. Confirm the new At a Glance card appears.
7. Confirm evidence excerpts match the original note.
8. Approve one suggested task and reject another.
9. Confirm the approved task appears in Tasks.
10. Delete the approved task and confirm the suggestion becomes Pending again.
11. Ask a follow-up question.
12. Edit the note and confirm the analysis becomes stale.
13. Refresh the insight and ask another question.
14. Delete the note and confirm approved workspace tasks remain.

## Review fixes included

- Fixed the create-note `request.form.get()` call that had an extra argument.
- Cleaned and consolidated the AI provider service.
- Added full user-friendly structured normalization.
- Added backward compatibility for older analyses.
- Added the missing task approval/rejection workflow.
- Added stale-analysis protection.
- Added failed follow-up question history.
- Added the missing complete Phase 6.1 SQL migration.
- Removed `.env`, `.git`, bytecode caches, and local database files from the returned project.
- Added `.env.example` and corrected `.gitignore` so the example remains shareable.
- Removed the duplicate `python-dotenv` requirement.
