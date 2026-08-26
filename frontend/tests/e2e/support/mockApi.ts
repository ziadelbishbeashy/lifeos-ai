import type { Page, Route } from "@playwright/test";

const user = { id: 1, name: "Mariam", email: "mariam@example.com" };

const project1 = {
  id: 1,
  title: "LifeOS",
  project_type: "Product",
  description: "Personal operating system for trustworthy work, knowledge, and AI-assisted execution.",
  goal: "Ship a dependable LifeOS V1 without losing trust or context.",
  tech_stack: "React, TypeScript, Flask, SQLAlchemy",
  project_folder: null,
  github_link: null,
  demo_link: null,
  start_date: "2026-08-01",
  deadline: "2026-09-30",
  status: "In Progress",
  priority: "High",
  current_phase: "Frontend stabilization",
  progress: 72,
  created_at: "2026-08-01T08:00:00Z",
  updated_at: "2026-08-25T10:00:00Z",
};

const project2 = {
  ...project1,
  id: 2,
  title: "DSD Outlet",
  project_type: "Deployment",
  description: "Launch-readiness workspace for the store deployment.",
  goal: "Reach production with repeatable deployment checks.",
  tech_stack: "Flask, SQL Server",
  deadline: "2026-08-28",
  priority: "Critical",
  current_phase: "Launch readiness",
  progress: 58,
};

const task1 = {
  id: 11,
  project_id: 1,
  project: { id: 1, title: "LifeOS" },
  title: "Add frontend regression coverage",
  description: "Protect the React layout and critical user flows with browser tests.",
  module: "Frontend",
  tags: "react,testing",
  importance: "High",
  difficulty: "Medium",
  deadline: "2026-08-27",
  status: "In Progress",
  priority_score: 92,
  reason: "Prevents repeated UI regressions.",
  reminder_enabled: false,
  reminder_type: "none",
  reminder_datetime: null,
  is_recurring: false,
  recurrence_type: "none",
  recurrence_interval: 1,
  recurrence_end_date: null,
  next_occurrence_date: null,
  created_at: "2026-08-24T12:00:00Z",
  completed_at: null,
};

const task2 = {
  ...task1,
  id: 12,
  project_id: 2,
  project: { id: 2, title: "DSD Outlet" },
  title: "Verify clean production database",
  description: "Prove migrations work from an empty production-like database.",
  module: "Deployment",
  tags: "database,release",
  importance: "Critical",
  difficulty: "High",
  deadline: "2026-08-26",
  status: "Pending",
  priority_score: 98,
};

const task3 = {
  ...task1,
  id: 13,
  project_id: null,
  project: null,
  title: "Review weekly priorities",
  description: "Review open work and pick the next meaningful action.",
  module: "General",
  tags: "planning",
  importance: "Medium",
  difficulty: "Low",
  deadline: null,
  status: "Completed",
  priority_score: 40,
  completed_at: "2026-08-24T18:00:00Z",
};

const projectCard = (project: typeof project1, overrides: Record<string, unknown> = {}) => ({
  ...project,
  task_progress: project.progress,
  total_tasks: 6,
  completed_tasks: 4,
  open_tasks: 2,
  overdue_tasks: 0,
  note_count: 5,
  health: { label: "On track", tone: "good", message: "No critical execution blockers are currently open." },
  next_task: task1,
  ...overrides,
});

const focusSessionBase = {
  id: 301,
  task_id: 11,
  task: { id: 11, title: task1.title, project: task1.project },
  title: task1.title,
  goal: "Finish the browser regression safety net.",
  planned_minutes: 25,
  actual_minutes: 0,
  elapsed_seconds: 12,
  status: "running",
  distraction_count: 0,
  goal_result: null,
  focus_rating: null,
  notes: null,
  started_at: "2026-08-25T15:00:00Z",
  completed_at: null,
  created_at: "2026-08-25T15:00:00Z",
  distractions: [] as Array<Record<string, unknown>>,
};

export type MockApiState = {
  focusSession: typeof focusSessionBase | null;
  questionHistory: Array<Record<string, unknown>>;
};

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

export async function installLifeosApiMock(page: Page): Promise<MockApiState> {
  const state: MockApiState = {
    focusSession: null,
    questionHistory: [
      {
        id: 801,
        question: "What is the immediate priority?",
        answer: "Stabilize the existing system before adding the next large feature.",
        sources: [{ page: 5, section: "R0 exit condition", evidence: "Full pytest must pass and critical workflows must have integration coverage." }],
        status: "Completed",
        error_message: null,
        created_at: "2026-08-25T10:30:00Z",
      },
    ],
  };

  await page.addInitScript(() => {
    localStorage.setItem("lifeos-theme", "dark");
    localStorage.removeItem("lifeos-focus-pending-settings");
  });

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === "/api/v1/session") return json(route, { authenticated: true, user });
    if (path === "/api/v1/csrf") return json(route, { csrf_token: "playwright-csrf" });
    if (path === "/api/v1/auth/logout") return json(route, { authenticated: false, user: null });

    if (path === "/api/v1/dashboard") {
      return json(route, {
        today: "2026-08-25",
        counts: {
          projects: 2,
          active_projects: 2,
          tasks: 8,
          general_tasks: 2,
          project_tasks: 6,
          open_tasks: 4,
          completed_tasks: 4,
          blocked_tasks: 1,
          overdue_tasks: 1,
          notes: 7,
          documents: 4,
        },
        completion_rate: 50,
        average_project_progress: 65,
        focus_task: task1,
        upcoming_tasks: [task2, task1],
        latest_projects: [project1, project2],
      });
    }

    if (path === "/api/v1/projects" && method === "GET") {
      return json(route, {
        items: [
          projectCard(project1),
          projectCard(project2, {
            health: { label: "Needs attention", tone: "warning", message: "A launch blocker is close to its deadline." },
            next_task: task2,
            overdue_tasks: 1,
          }),
        ],
        counts: { total: 2, active: 2, attention: 1, completed: 0 },
      });
    }
    if (path === "/api/v1/projects" && method === "POST") return json(route, { item: project1 }, 201);
    if (path === "/api/v1/projects/1") {
      return json(route, {
        project: project1,
        tasks: [task1, task3],
        recent_notes: [
          { id: 41, project_id: 1, title: "R0 checkpoint", content: "All backend regression tests are green.", note_type: "Project", is_pinned: true, updated_at: "2026-08-25T09:00:00Z" },
        ],
        documents: [
          { id: 101, project_id: 1, filename: "LifeOS_Master_Plan.pdf", version_label: "v1", version_number: 1, is_current_version: true, uploaded_at: "2026-08-24T12:00:00Z", has_text: true, summary: "LifeOS architecture and reliability plan." },
        ],
        metrics: {
          total_tasks: 2,
          completed_tasks: 1,
          pending_tasks: 0,
          in_progress_tasks: 1,
          blocked_tasks: 0,
          overdue_tasks: 0,
          due_soon_tasks: 1,
          task_progress: 50,
          notes_count: 1,
          document_count: 1,
          searchable_document_count: 1,
        },
        project_health: { label: "On track", tone: "good", message: "Execution is healthy." },
        days_to_deadline: 36,
        next_task: task1,
        project_question_history: [],
        document_suggestions: [],
        pending_document_suggestion_count: 0,
      });
    }

    if (path === "/api/v1/tasks" && method === "GET") {
      return json(route, {
        items: [task1, task2, task3],
        projects: [project1, project2].map(({ id, title, status, priority, progress, deadline }) => ({ id, title, status, priority, progress, deadline })),
        module_names: ["Frontend", "Deployment", "General"],
        counts: {
          total: 3,
          completed: 1,
          pending: 1,
          in_progress: 1,
          blocked: 0,
          general: 1,
          project: 2,
          recurring: 0,
          overdue: 0,
          due_soon: 2,
        },
      });
    }
    if (path === "/api/v1/tasks" && method === "POST") return json(route, { item: task1 }, 201);
    if (/^\/api\/v1\/tasks\/\d+\/toggle$/.test(path)) return json(route, { item: { ...task1, status: "Completed" }, message: "Task completed." });
    if (/^\/api\/v1\/tasks\/\d+$/.test(path) && method === "PATCH") return json(route, { item: task1 });
    if (/^\/api\/v1\/tasks\/\d+$/.test(path) && method === "DELETE") return json(route, { deleted: true, title: task1.title, project_id: 1 });

    if (path.startsWith("/api/v1/notes") && path === "/api/v1/notes") {
      return json(route, {
        items: [
          { id: 41, project_id: 1, project: { id: 1, title: "LifeOS" }, title: "R0 checkpoint", content: "The full regression suite is green and the architecture is separated.", note_type: "Project", is_pinned: true, updated_at: "2026-08-25T09:00:00Z", created_at: "2026-08-24T09:00:00Z" },
          { id: 42, project_id: null, project: null, title: "Interview review", content: "Keep explanations compact and connected to practical examples.", note_type: "General", is_pinned: false, updated_at: "2026-08-24T18:00:00Z", created_at: "2026-08-24T18:00:00Z" },
        ],
        pinned: [
          { id: 41, project_id: 1, project: { id: 1, title: "LifeOS" }, title: "R0 checkpoint", content: "The full regression suite is green and the architecture is separated.", note_type: "Project", is_pinned: true, updated_at: "2026-08-25T09:00:00Z", created_at: "2026-08-24T09:00:00Z" },
        ],
        regular: [],
        projects: [{ id: 1, title: "LifeOS" }, { id: 2, title: "DSD Outlet" }],
        note_types: ["General", "Project", "Research"],
        filters: { q: "", type: "all", project: "all" },
      });
    }
    if (path === "/api/v1/notes/41") {
      return json(route, {
        note: { id: 41, title: "R0 checkpoint", content: "The full regression suite is green and the architecture is separated.", note_type: "Project", project: { id: 1, title: "LifeOS" }, is_pinned: true },
        latest_analysis: null,
        latest_failed_analysis: null,
        task_suggestions: [],
        question_history: [],
        insights: {},
        project_context: {},
        analysis_is_stale: false,
      });
    }

    if (path === "/api/v1/focus" && method === "GET") {
      return json(route, {
        tasks: [
          { id: 11, title: task1.title, project: task1.project, deadline: task1.deadline, importance: task1.importance },
          { id: 12, title: task2.title, project: task2.project, deadline: task2.deadline, importance: task2.importance },
        ],
        active_session: state.focusSession,
        elapsed_seconds: state.focusSession?.elapsed_seconds ?? 0,
        today_minutes: 50,
      });
    }
    if (path === "/api/v1/focus/start" && method === "POST") {
      state.focusSession = { ...focusSessionBase };
      return json(route, { session: state.focusSession }, 201);
    }
    const focusAction = path.match(/^\/api\/v1\/focus\/(\d+)\/(pause|resume|extend|review|cancel|finish)$/);
    if (focusAction && state.focusSession) {
      const action = focusAction[2];
      if (action === "pause") state.focusSession = { ...state.focusSession, status: "paused", elapsed_seconds: 45 };
      if (action === "resume") state.focusSession = { ...state.focusSession, status: "running" };
      if (action === "extend") state.focusSession = { ...state.focusSession, planned_minutes: state.focusSession.planned_minutes + 5 };
      if (action === "cancel") state.focusSession = null;
      if (action === "finish") state.focusSession = null;
      return json(route, action === "review"
        ? { session: state.focusSession, review_requested: true }
        : { session: state.focusSession });
    }
    if (/^\/api\/v1\/focus\/\d+\/distractions$/.test(path) && state.focusSession) {
      const item = { id: 901, content: "Remember the deployment checklist", captured_at: "2026-08-25T15:05:00Z", converted_task_id: null };
      state.focusSession = { ...state.focusSession, distraction_count: 1, distractions: [item] };
      return json(route, { item }, 201);
    }
    if (/^\/api\/v1\/focus\/distractions\/\d+\/convert$/.test(path)) return json(route, { created_task_id: 99 });
    if (path === "/api/v1/focus/insights") {
      return json(route, {
        week_minutes: 210,
        week_sessions: 5,
        week_distractions: 3,
        average_rating: 4.4,
        daily_data: [
          { label: "Mon", date: "2026-08-24", minutes: 50, height: 72 },
          { label: "Tue", date: "2026-08-25", minutes: 75, height: 100 },
          { label: "Wed", date: "2026-08-26", minutes: 35, height: 47 },
          { label: "Thu", date: "2026-08-27", minutes: 25, height: 34 },
          { label: "Fri", date: "2026-08-28", minutes: 25, height: 34 },
          { label: "Sat", date: "2026-08-29", minutes: 0, height: 0 },
          { label: "Sun", date: "2026-08-30", minutes: 0, height: 0 },
        ],
        project_data: [{ name: "LifeOS", minutes: 150 }, { name: "DSD Outlet", minutes: 60 }],
        recent_sessions: [{ ...focusSessionBase, id: 302, status: "completed", actual_minutes: 50, focus_rating: 5, completed_at: "2026-08-25T14:00:00Z" }],
      });
    }

    if (path === "/api/v1/analytics") {
      return json(route, {
        range: { label: "This month", start_date: "2026-08-01", end_date: "2026-08-31" },
        summary: { completed_in_period: 14, completion_rate: 62, open_tasks: 4, total_tasks: 18, focus_label: "3h 30m", focus_minutes: 210, average_session_label: "42 min", focus_sessions: 5, overdue_tasks: 1, blocked_tasks: 1, active_projects: 2, recurring_tasks: 0 },
        comparisons: { completed: { label: "+4 vs prior period" }, focus: { label: "+45 min vs prior period" } },
        task_series: [
          { label: "W1", title: "Week 1", created: 4, completed: 3, created_height: 62, completed_height: 48 },
          { label: "W2", title: "Week 2", created: 6, completed: 5, created_height: 92, completed_height: 78 },
          { label: "W3", title: "Week 3", created: 3, completed: 4, created_height: 46, completed_height: 62 },
        ],
        status_data: { total: 18, gradient: "conic-gradient(#7c72f2 0 55%, #3bd7a0 55% 77%, #f59e0b 77% 88%, #ef4444 88% 100%)", segments: [{ name: "Open", count: 10, color: "#7c72f2" }, { name: "Completed", count: 4, color: "#3bd7a0" }, { name: "Pending", count: 2, color: "#f59e0b" }, { name: "Blocked", count: 2, color: "#ef4444" }] },
        focus_series: [
          { label: "Mon", title: "Monday", formatted: "50m", height: 67 },
          { label: "Tue", title: "Tuesday", formatted: "75m", height: 100 },
          { label: "Wed", title: "Wednesday", formatted: "35m", height: 47 },
        ],
        priority_data: [{ name: "Critical", count: 2, width: 80, color: "#ef4444" }, { name: "High", count: 5, width: 65, color: "#f59e0b" }, { name: "Medium", count: 7, width: 48, color: "#7c72f2" }],
        projects: [{ id: 1, title: "LifeOS", status: "In Progress", priority: "High", progress: 72, completed_tasks: 4, total_tasks: 6, open_tasks: 2, overdue_tasks: 0, blocked_tasks: 0, focus_label: "2h 30m", deadline_label: "36 days", deadline_tone: "good" }],
        insights: [{ tone: "warning", title: "One deadline needs attention", text: "DSD Outlet has a critical task due soon." }, { tone: "good", title: "Focus time is improving", text: "You added 45 focused minutes compared with the prior period." }],
      });
    }

    if (path === "/api/v1/notifications/settings") {
      return json(route, {
        email_configured: true,
        recent_logs: [],
        preferences: {
          email_enabled: true,
          task_reminders_enabled: true,
          custom_task_reminders_enabled: true,
          overdue_alerts_enabled: true,
          project_deadline_alerts_enabled: true,
          project_risk_alerts_enabled: true,
          daily_checkup_enabled: true,
          weekly_summary_enabled: true,
          monthly_analytics_enabled: false,
          task_reminder_days_before: 1,
          project_reminder_days_before: 3,
          daily_checkup_time: "08:00",
          weekly_summary_day: 6,
          weekly_summary_time: "18:00",
          monthly_report_day: 1,
          monthly_report_time: "08:00",
          quiet_hours_start: "22:00",
          quiet_hours_end: "07:00",
        },
      });
    }
    if (path === "/api/v1/notifications/history") return json(route, { items: [{ id: 1, subject: "Daily LifeOS checkup", notification_type: "daily", status: "Sent", sent_to: user.email, sent_at: "2026-08-25T08:00:00Z" }] });
    if (path.startsWith("/api/v1/notifications/email/")) return json(route, { message: "Email action completed." });

    if (path === "/api/v1/documents" && method === "GET") {
      return json(route, {
        max_upload_bytes: 10 * 1024 * 1024,
        projects: [{ id: 1, title: "LifeOS" }, { id: 2, title: "DSD Outlet" }],
        items: [
          { id: 101, project_id: 1, project: { id: 1, title: "LifeOS" }, filename: "LifeOS_Master_Plan.pdf", version_label: "v1", uploaded_at: "2026-08-24T12:00:00Z", has_text: true, summary: "LifeOS architecture, reliability gates, and product roadmap." },
          { id: 102, project_id: 2, project: { id: 2, title: "DSD Outlet" }, filename: "Launch_Readiness.pdf", version_label: "v2", uploaded_at: "2026-08-23T12:00:00Z", has_text: true, summary: "Launch readiness plan with deployment risks and actions." },
        ],
      });
    }
    if (path === "/api/v1/documents/101") {
      return json(route, documentDetailFixture(state));
    }
    if (path === "/api/v1/documents/101/detect-type") {
      return json(route, { detection: { document_type_key: "project_plan", document_type_label: "Project Plan", confidence: "high", reason: "The document contains objectives, milestones, risks, and a delivery roadmap." } });
    }
    if (path === "/api/v1/documents/101/analyze") return json(route, documentDetailFixture(state));
    if (path === "/api/v1/documents/101/questions" && method === "POST") {
      const item = { id: 802, question: "What should happen next?", answer: "Finish the frontend reliability gate, then continue the roadmap.", sources: [{ page: 5, section: "R0 exit condition", evidence: "Critical workflows must have integration coverage." }], status: "Completed", error_message: null, created_at: "2026-08-25T16:00:00Z" };
      state.questionHistory = [item, ...state.questionHistory];
      return json(route, { item }, 201);
    }
    if (path === "/api/v1/documents/101/search") {
      return json(route, { query: url.searchParams.get("q") || "", mode: "hybrid", result_count: 1, semantic_fallback: false, items: [{ rank: 1, chunk_id: 501, page_start: 5, page_end: 5, page_label: "Page 5", section: "R0 exit condition", preview: "Full pytest must pass, critical workflows must have integration coverage.", exact_phrase: false, method_label: "Hybrid match", match_strength: "Strong" }] });
    }
    if (path === "/api/v1/documents/comparisons") {
      return json(route, {
        documents: [{ id: 101, filename: "LifeOS_Master_Plan.pdf", project_id: 1, version_label: "v1" }, { id: 102, filename: "Launch_Readiness.pdf", project_id: 2, version_label: "v2" }],
        items: [],
      });
    }

    // Mutating endpoints not explicitly exercised by layout tests still return
    // deterministic JSON so buttons/forms cannot hang because of an unmocked API.
    if (["POST", "PATCH", "PUT", "DELETE"].includes(method)) return json(route, { ok: true, message: "Mock action completed." });

    return json(route, { error: "Unmocked endpoint", message: `${method} ${path} is not defined in the Playwright fixture.` }, 404);
  });

  return state;
}

function documentDetailFixture(state: MockApiState) {
  const source = { page: 5, section: "R0 exit condition", evidence: "Full pytest must pass, critical workflows must have integration coverage, and provider behavior must be deterministic in tests." };
  return {
    document: { id: 101, filename: "LifeOS_Master_Plan.pdf", project: { id: 1, title: "LifeOS" }, version_label: "v1", is_current_version: true, document_type: "Project Plan" },
    analysis: { id: 701, status: "Completed", summary: "LifeOS is ready to move from reliability stabilization into controlled product development.", insights: { summary: "A reliability-first project plan." } },
    latest_attempt: null,
    overview: { analysis: { summary: "A reliability-first project plan." } },
    type_workspace: {
      sections: [
        { key: "objectives", label: "Objectives", count: 2, items: [{ title: "Stabilize the platform", detail: "Make regressions observable before adding new features.", source }] },
        { key: "risks", label: "Risks", count: 1, items: [{ title: "Frontend regression risk", detail: "Large CSS changes can break unrelated screens.", source }] },
      ],
    },
    analysis_experience: {
      status_label: "Analysis saved",
      overview_title: "Project Plan at a glance",
      type_adjusted: false,
      focus: "Finish the frontend reliability gate before adding the next major feature.",
      focus_source: source,
      attention_count: 1,
      attention: [{ label: "Risk", title: "Frontend changes need browser coverage", detail: "Build tests alone cannot detect collapsed grids or blank screens.", tone: "warning", source }],
      action_count: 2,
      actions: [{ title: "Add Playwright smoke coverage", detail: "Exercise critical React screens in a real browser.", priority: "High", source }, { title: "Freeze approved visual baselines", detail: "Use screenshots only after the UI is visually approved.", priority: "Medium", source }],
      questions: [{ question: "What could break the UI again?" }, { question: "What should happen after the stability gate?" }],
      plan_sections: [{ label: "Objectives", count: 2, preview: "Reliability and controlled delivery", source }, { label: "Risks", count: 1, preview: "Regression risk", source }],
    },
    suggestions: [{ id: 601, title: "Add browser regression coverage", description: "Protect critical screens and layouts.", priority: "High", deadline: null, source, status: "Pending", lifecycle_label: "Ready" }],
    question_history: state.questionHistory,
    document_type_choices: [{ key: "project_plan", label: "Project Plan" }, { key: "research_paper", label: "Research Paper" }],
    version_history: { versions: [{ id: 101, version_label: "v1", filename: "LifeOS_Master_Plan.pdf" }] },
    pdf_url: "/api/v1/documents/101/file",
  };
}
