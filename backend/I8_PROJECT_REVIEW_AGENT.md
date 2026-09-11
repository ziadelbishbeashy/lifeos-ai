# I8 — Constrained Project Review Agent

I8 is the first agentic LifeOS workflow. It is intentionally **read-only**.

## Goal

Move Ask LifeOS from summarising project state to inspecting trusted state and
ranking what deserves attention next.

## Trust boundary

The agent does not receive SQL access and does not choose arbitrary tools. It
reuses the existing reviewed project context plan:

1. project state
2. project tasks / deadlines
3. current document freshness
4. current structured document findings
5. deterministic priority ranking

Document findings may support a recommendation, but never directly create a
Task or mutate trusted application state.

## Priority order

The deterministic ranking favors:

1. blocked tasks
2. overdue tasks / overdue project deadline
3. near deadlines
4. current structured document risks
5. stale document intelligence
6. confirmed document action items
7. missing information
8. the strongest open next task
9. an active project with no concrete next task

Internal numeric ranking scores stay diagnostic-only and are not exposed in the
normal Ask LifeOS response.

## Ask LifeOS examples

- `What should I focus on in LifeOS?` -> `project_focus`
- `What should I focus on in my project?` -> clarification when needed
- clarification reply `all` -> `portfolio_focus`
- `Review all my projects and tell me what I should focus on.` -> `portfolio_focus`

The API returns `response_mode=agent_verified` and a bounded public `agent`
payload containing evidence-backed priorities.

## CLI

```powershell
python -m flask --app app intelligence-project-agent --user-id 1 --project-id 1
python -m flask --app app intelligence-portfolio-agent --user-id 1
```

CLI diagnostics include the reviewed steps and internal rank score. The normal
frontend/API does not expose those internals.

## Not part of I8

- no autonomous database writes
- no task creation
- no deadline changes
- no background agent loop
- no destructive actions

Those belong behind the future Action + Confirmation Engine.

## Clarification intent preservation

Attention/prioritization wording such as `Review my project and tell me what needs attention` is classified as `project_focus`. If more than one owned project exists, the clarification preserves that intent; choosing `all` continues as `portfolio_focus` and runs the portfolio review agent rather than falling back to the passive portfolio summary.
