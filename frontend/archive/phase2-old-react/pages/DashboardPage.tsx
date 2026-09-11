import { useQuery } from "@tanstack/react-query";
import type { CSSProperties, ReactNode } from "react";
import { Link } from "react-router-dom";
import { apiGet } from "../api/client";
import type { DashboardData, DashboardTask } from "../api/types";
import { useSession } from "../auth/session";

function formatDate(value: string | null) {
  if (!value) return "No deadline";
  const date = new Date(`${value}T00:00:00`);
  return new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
  }).format(date);
}

function taskScope(task: DashboardTask) {
  return task.project?.title ?? "General Workspace";
}

export function DashboardPage() {
  const session = useSession();
  const dashboard = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => apiGet<DashboardData>("/api/v1/dashboard"),
  });

  if (dashboard.isPending) {
    return (
      <div className="page-state panel-card">
        <div className="spinner" />
        <div>
          <strong>Building your dashboard</strong>
          <span>Loading projects, tasks and execution signals…</span>
        </div>
      </div>
    );
  }

  if (dashboard.isError || !dashboard.data) {
    return (
      <div className="page-state panel-card error-state">
        <strong>Dashboard unavailable</strong>
        <span>LifeOS could not load your workspace data.</span>
        <button className="secondary-button" onClick={() => dashboard.refetch()}>Try again</button>
      </div>
    );
  }

  const data = dashboard.data;
  const firstName = session.data?.user?.name?.split(/\s+/)[0] ?? "there";

  return (
    <section className="dashboard-page">
      <div className="dashboard-hero-grid">
        <div className="dashboard-hero-copy">
          <span className="eyebrow">Welcome back, {firstName}</span>
          <h1>Turn today into <em>measurable progress.</em></h1>
          <p className="lead">
            Projects, tasks and execution signals are gathered here so you can
            focus on the next meaningful action.
          </p>
          <div className="hero-actions">
            <Link className="primary-button" to="/projects">+ Create Project</Link>
            <Link className="secondary-button" to="/projects">View Workspace</Link>
          </div>
        </div>

        <article className="readiness-card">
          <div className="readiness-heading">
            <div>
              <span>Execution readiness</span>
              <strong>{data.completion_rate}%</strong>
            </div>
            <div
              className="ring"
              style={{ "--progress": `${data.completion_rate * 3.6}deg` } as CSSProperties}
            >
              <span>{data.completion_rate}%</span>
            </div>
          </div>
          <div className="readiness-metrics">
            <div><span>Active projects</span><strong>{data.counts.active_projects}</strong></div>
            <div><span>Open actions</span><strong>{data.counts.open_tasks}</strong></div>
            <div><span>Average progress</span><strong>{data.average_project_progress}%</strong></div>
          </div>
          <p>
            {data.counts.overdue_tasks > 0
              ? `${data.counts.overdue_tasks} overdue task${data.counts.overdue_tasks === 1 ? "" : "s"} need attention.`
              : data.counts.open_tasks > 0
                ? "Your workspace is clear of overdue work."
                : "Add tasks to begin measuring execution health."}
          </p>
        </article>
      </div>

      <div className="stat-grid">
        <Stat label="Active Projects" value={data.counts.active_projects} meta={`${data.counts.projects} total workspaces`} tone="purple" />
        <Stat label="Open Tasks" value={data.counts.open_tasks} meta={`${data.counts.tasks} total actions`} tone="blue" />
        <Stat label="Completed" value={data.counts.completed_tasks} meta={`${data.completion_rate}% completion rate`} tone="green" />
        <Stat label="Blocked Tasks" value={data.counts.blocked_tasks} meta={`${data.counts.overdue_tasks} overdue`} tone="red" />
      </div>

      <div className="dashboard-main-grid">
        <article className="panel-card focus-panel">
          <PanelHeading kicker="Smart focus" title="Today's Priority" trailing={<span className="live-pill"><i /> Live</span>} />
          {data.focus_task ? (
            <div className="focus-task">
              <div className="focus-topline">
                <span className="priority-pill">{data.focus_task.importance ?? "Medium"} priority</span>
                <span className="status-pill">{data.focus_task.status}</span>
              </div>
              <h3>{data.focus_task.title}</h3>
              <p>{data.focus_task.description || "This action was selected from your active work based on status, importance and deadline."}</p>
              <div className="task-meta-grid">
                <div><span>Scope</span><strong>{taskScope(data.focus_task)}</strong></div>
                <div><span>Module</span><strong>{data.focus_task.module || "General"}</strong></div>
                <div><span>Deadline</span><strong>{formatDate(data.focus_task.deadline)}</strong></div>
              </div>
              <div className="panel-actions">
                <Link className="primary-button compact" to="/tasks">Open Task Center</Link>
                <Link className="secondary-button compact" to="/tasks">View Tasks</Link>
              </div>
            </div>
          ) : (
            <EmptyState title="No active priority task" text="Add a task or reopen an existing one to create your next focus." />
          )}
        </article>

        <article className="panel-card health-panel">
          <PanelHeading kicker="Workspace signal" title="Execution Health" />
          <div className="health-layout">
            <div
              className="ring large"
              style={{ "--progress": `${data.completion_rate * 3.6}deg` } as CSSProperties}
            >
              <span><strong>{data.completion_rate}%</strong><small>complete</small></span>
            </div>
            <div className="health-copy">
              <div><span>Project progress</span><strong>{data.average_project_progress}%</strong></div>
              <div><span>Notes captured</span><strong>{data.counts.notes}</strong></div>
              <div><span>Documents</span><strong>{data.counts.documents}</strong></div>
            </div>
          </div>
        </article>

        <article className="panel-card projects-panel">
          <PanelHeading kicker="Workspaces" title="Recent Projects" trailing={<Link to="/projects" className="text-link">View all</Link>} />
          {data.latest_projects.length ? (
            <div className="project-list">
              {data.latest_projects.map((project) => (
                <Link to={`/projects/${project.id}`} className="project-row" key={project.id}>
                  <span className="project-avatar">{project.title[0]?.toUpperCase()}</span>
                  <div className="project-main">
                    <div className="project-heading">
                      <div><strong>{project.title}</strong><span>{project.current_phase || project.project_type || "Project workspace"}</span></div>
                      <span className="status-pill">{project.status}</span>
                    </div>
                    <div className="progress-row"><div className="progress-track"><span style={{ width: `${project.progress}%` }} /></div><strong>{project.progress}%</strong></div>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState title="No projects created" text="Create your first workspace to start organizing execution." />
          )}
        </article>

        <article className="panel-card deadlines-panel">
          <PanelHeading kicker="Time awareness" title="Upcoming Deadlines" trailing={<span className="date-chip">{formatDate(data.today)}</span>} />
          {data.upcoming_tasks.length ? (
            <div className="deadline-list">
              {data.upcoming_tasks.map((task) => (
                <Link to="/tasks" className="deadline-row" key={task.id}>
                  <div className="deadline-date"><strong>{formatDate(task.deadline).split(" ")[0]}</strong><span>{formatDate(task.deadline).split(" ")[1]}</span></div>
                  <div><strong>{task.title}</strong><span>{taskScope(task)}</span></div>
                  <span className="status-pill">{task.status}</span>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState title="No upcoming deadlines" text="Your current open work has no scheduled deadlines." />
          )}
        </article>
      </div>
    </section>
  );
}

function Stat({ label, value, meta, tone }: { label: string; value: number; meta: string; tone: string }) {
  return (
    <article className={`stat-card ${tone}`}>
      <span className="stat-dot" />
      <div><span>{label}</span><strong>{value}</strong><small>{meta}</small></div>
    </article>
  );
}

function PanelHeading({ kicker, title, trailing }: { kicker: string; title: string; trailing?: ReactNode }) {
  return (
    <div className="panel-heading">
      <div><span className="panel-kicker">{kicker}</span><h2>{title}</h2></div>
      {trailing}
    </div>
  );
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return <div className="empty-state"><span>✓</span><strong>{title}</strong><p>{text}</p></div>;
}
