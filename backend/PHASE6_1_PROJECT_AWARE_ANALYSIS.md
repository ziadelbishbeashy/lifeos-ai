# Phase 6.1 — Project-Aware AI Notes

## Behavior

- General notes use note-only analysis.
- Any note linked to a project automatically uses project-aware analysis.
- No extra checkbox is required.

## Context supplied to AI

The linked-project snapshot is scoped to the logged-in user and includes:

- Project title, description, goal, type, technology stack, status, priority, phase, progress, start date, and deadline.
- Project task IDs, titles, compact descriptions, modules, statuses, priorities, difficulties, deadlines, completion dates, and priority scores.
- Task status totals.
- Up to 10 recent related project notes using their latest overview when available.

For very large projects, the 150 most relevant tasks are used, prioritizing blocked, in-progress, pending, and deadline-sensitive work. The UI shows when context was limited.

## Project-aware output

The insight dashboard can now show:

- Project alignment
- Current project situation
- Existing task matches
- Recommendations to continue or update existing tasks
- Work that is not yet tracked
- A project-aware next step and action plan
- Only genuinely new task suggestions

AI task IDs are validated against the exact owned project-task snapshot. Invented or unrelated task references are discarded.

## Duplicate prevention

The prompt instructs the provider not to create duplicate tasks. The service also removes exact-title task suggestions that already exist in the supplied project context.

## Follow-up questions

Ask LifeOS now uses the current project snapshot for linked notes. It can answer questions such as:

- Which note items already have project tasks?
- What should I work on next based on current status?
- What work is not tracked yet?
- Is the note aligned with the current project phase?

## Freshness

The analysis fingerprint now includes the current note and project snapshot. Changes to project metadata, task status, task deadlines, or recent related notes mark the saved insight as outdated and require a refresh before grounded follow-up questions.

## Database

No new migration is required for this update. Project-aware fields are stored inside the existing `note_ai_analyses.insights_json` column.
