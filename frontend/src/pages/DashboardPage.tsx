import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type CSSProperties } from "react";
import { apiGet, apiPost } from "../api/client";
import type {
  DashboardData,
  DashboardTask,
  HomeActivityItem,
  HomeInsightItem,
  HomeIntelligenceData,
  IntelligenceActionProposal,
  TodayIntelligenceData,
  TodayPriority,
} from "../api/types";
import { useSession } from "../auth/session";

function formatDay(value: string | null | undefined) {
  if (!value) return { day: "--", month: "---" };
  const date = new Date(`${value}T00:00:00`);
  return { day: String(date.getDate()).padStart(2, "0"), month: date.toLocaleString(undefined, { month: "short" }) };
}
function scope(task: DashboardTask) { return task.project?.title || "General Workspace"; }
function progressStyle(value: number): CSSProperties { return { ["--progress" as string]: value } as CSSProperties; }
function compactDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Recently";
  return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export function DashboardPage() {
  const session = useSession();
  const queryClient = useQueryClient();
  const [proposal, setProposal] = useState<IntelligenceActionProposal | null>(null);
  const [proposalBusy, setProposalBusy] = useState(false);
  const [proposalError, setProposalError] = useState<string | null>(null);

  const query = useQuery({ queryKey: ["dashboard"], queryFn: () => apiGet<DashboardData>("/api/v1/dashboard") });
  const homeQuery = useQuery({ queryKey: ["intelligence", "home"], queryFn: () => apiGet<{ home: HomeIntelligenceData }>("/api/v1/intelligence/home") });

  if (query.isPending) return <div className="dashboard-empty-state"><div className="empty-state-icon">…</div><h3>Opening dashboard</h3><p>Loading your workspace overview…</p></div>;
  if (query.isError || !query.data) return <div className="dashboard-empty-state"><div className="empty-state-icon">!</div><h3>Dashboard unavailable</h3><p>LifeOS could not load your workspace data.</p><button className="dashboard-secondary-action compact" onClick={() => query.refetch()}>Try again</button></div>;

  const data = query.data;
  const home = homeQuery.data?.home;
  const today = home?.focus;
  const firstName = session.data?.user?.name?.split(/\s+/)[0] || "there";
  const overdue = data.counts.overdue_tasks;

  async function createProposal(priority: TodayPriority, actionType: string) {
    if (proposalBusy || proposal?.status === "pending" || proposal?.status === "executing") return;
    setProposalBusy(true);
    setProposalError(null);
    try {
      const response = await apiPost<{ proposal: IntelligenceActionProposal }>("/api/v1/intelligence/action-proposals", {
        action_type: actionType,
        priority,
      });
      setProposal(response.proposal);
    } catch (error) {
      setProposalError(error instanceof Error ? error.message : "LifeOS could not prepare this action.");
    } finally {
      setProposalBusy(false);
    }
  }

  async function resolveProposal(mode: "confirm" | "dismiss") {
    if (!proposal || proposalBusy || proposal.status !== "pending") return;
    setProposalBusy(true);
    setProposalError(null);
    try {
      const response = await apiPost<{ proposal: IntelligenceActionProposal }>(`/api/v1/intelligence/action-proposals/${proposal.id}/${mode}`, {});
      setProposal(response.proposal);
      if (mode === "confirm") {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
          queryClient.invalidateQueries({ queryKey: ["intelligence", "home"] }),
        ]);
      }
    } catch (error) {
      setProposalError(error instanceof Error ? error.message : "LifeOS could not complete this action.");
    } finally {
      setProposalBusy(false);
    }
  }

  return <>
    <section className="dashboard-hero intelligent-home-hero">
      <div className="dashboard-hero-copy">
        <span className="dashboard-eyebrow">Verified workspace intelligence · Welcome back, {firstName}</span>
        <h1>Here’s what <span>matters today.</span></h1>
        <p>{home ? `${home.briefing.headline}. ${home.briefing.summary}` : "Your projects, tasks and execution signals are gathered here so you can focus on the next meaningful action."}</p>
        <div className="dashboard-hero-actions"><a href="/ask" className="dashboard-primary-action">Ask LifeOS</a><a href="/tasks" className="dashboard-secondary-action">Open Tasks</a><a href="/projects" className="dashboard-secondary-action">View Workspace</a></div>
      </div>
      {home ? <HomeSignalsCard home={home} completionRate={data.completion_rate} /> : <div className="hero-execution-card">
        <div className="execution-card-heading"><div><span>Execution readiness</span><strong>{data.completion_rate}%</strong></div><div className="mini-progress-ring" style={progressStyle(data.completion_rate)} aria-label={`${data.completion_rate} percent task completion`}><span /></div></div>
        <div className="execution-card-metrics"><div><span>Active projects</span><strong>{data.counts.active_projects}</strong></div><div><span>Open actions</span><strong>{data.counts.open_tasks}</strong></div><div><span>Average progress</span><strong>{data.average_project_progress}%</strong></div></div>
        <p>{overdue ? `${overdue} overdue task${overdue === 1 ? "" : "s"} need attention.` : data.counts.open_tasks ? "Your workspace is clear of overdue work." : "Add tasks to begin measuring execution health."}</p>
      </div>}
    </section>

    <section className="dashboard-stat-grid" aria-label="Workspace statistics">
      <StatCard tone="purple" title="Active Projects" value={data.counts.active_projects} detail={`${data.counts.projects} total workspaces`} icon="M3 6.5A2.5 2.5 0 0 1 5.5 4H9l2 2h7.5A2.5 2.5 0 0 1 21 8.5v8A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5v-10Z" />
      <StatCard tone="blue" title="Open Tasks" value={data.counts.open_tasks} detail={`${data.counts.tasks} total actions`} icon="M9 5h11v2H9V5Zm0 6h11v2H9v-2Zm0 6h11v2H9v-2ZM4.5 4A1.5 1.5 0 1 1 3 5.5 1.5 1.5 0 0 1 4.5 4Zm0 6A1.5 1.5 0 1 1 3 11.5 1.5 1.5 0 0 1 4.5 10Zm0 6A1.5 1.5 0 1 1 3 17.5 1.5 1.5 0 0 1 4.5 16Z" />
      <StatCard tone="green" title="Completed" value={data.counts.completed_tasks} detail={`${data.completion_rate}% completion rate`} icon="m9.5 16.2-3.7-3.7L4.4 14l5.1 5.1L20 8.6 18.6 7.2 9.5 16.2Z" />
      <StatCard tone="red" title="Blocked Tasks" value={data.counts.blocked_tasks} detail={`${data.counts.overdue_tasks} overdue`} icon="M11 7h2v6h-2V7Zm0 8h2v2h-2v-2Zm1-13 10 18H2L12 2Zm0 4.1L5.4 18h13.2L12 6.1Z" />
    </section>

    <section className="dashboard-main-grid">
      <article className="dashboard-panel focus-panel today-intelligence-panel">
        <div className="dashboard-panel-heading"><div><span className="panel-kicker">LifeOS intelligence</span><h2>Your Focus Today</h2></div>{home?.verified_from_state ? <span className="today-trust-badge"><i />Verified state</span> : <span className="live-status"><i />Live</span>}</div>
        {homeQuery.isPending ? <div className="today-intelligence-loading"><span /><div><strong>Reviewing your workspace</strong><p>Checking projects, tasks, deadlines, document signals and recent changes…</p></div></div> : today ? <TodayIntelligence today={today} onAction={createProposal} busy={proposalBusy || proposal?.status === "pending" || proposal?.status === "executing"} /> : data.focus_task ? <div className="focus-task-card"><div className="focus-task-topline"><span className={`focus-importance importance-${(data.focus_task.importance || "medium").toLowerCase()}`}>{data.focus_task.importance || "Medium"} priority</span><span className="focus-status">{data.focus_task.status}</span></div><h3>{data.focus_task.title}</h3><p>{data.focus_task.description || "This action has been selected from your active work based on status, importance and deadline."}</p><div className="focus-task-meta"><span><small>Scope</small><strong>{scope(data.focus_task)}</strong></span><span><small>Module</small><strong>{data.focus_task.module || "General"}</strong></span><span><small>Deadline</small><strong>{data.focus_task.deadline || "No deadline"}</strong></span></div><div className="focus-task-actions"><a href={data.focus_task.project ? `/projects/${data.focus_task.project.id}` : "/tasks"} className="dashboard-primary-action compact">{data.focus_task.project ? "Open Project" : "Open Task Center"}</a><a href="/tasks" className="dashboard-secondary-action compact">Edit Task</a></div></div> : <Empty title="No active priority task" text="Add a task or reopen an existing one to create your next focus." action="Open Projects" href="/projects" />}
        {proposal ? <HomeActionProposal proposal={proposal} busy={proposalBusy} error={proposalError} onConfirm={() => void resolveProposal("confirm")} onDismiss={() => void resolveProposal("dismiss")} /> : proposalError ? <div className="home-action-error">{proposalError}</div> : null}
      </article>

      <article className="dashboard-panel health-panel">
        <div className="dashboard-panel-heading"><div><span className="panel-kicker">Workspace signal</span><h2>Execution Health</h2></div></div>
        <div className="health-ring-layout"><div className="progress-ring" style={progressStyle(data.completion_rate)}><div className="progress-ring-inner"><strong>{data.completion_rate}%</strong><span>complete</span></div></div><div className="health-breakdown"><div><span><i className="health-dot completed-dot" />Completed</span><strong>{data.counts.completed_tasks}</strong></div><div><span><i className="health-dot open-dot" />Open</span><strong>{data.counts.open_tasks}</strong></div><div><span><i className="health-dot blocked-dot" />Blocked</span><strong>{data.counts.blocked_tasks}</strong></div><p className="health-message">{overdue ? `${overdue} overdue task${overdue === 1 ? "" : "s"} need attention.` : "No overdue tasks right now."}</p></div></div>
      </article>
    </section>

    {home ? <section className="home-intelligence-grid" aria-label="Today intelligence details">
      <HomeInsightCard title="Documents to Review" kicker="Document Brain" summary={home.documents.summary} items={home.documents.items} empty="No stale or missing document analysis right now." href="/documents" />
      <HomeStudyCard home={home} />
      <HomeActivityCard items={home.activity.items} total={home.activity.total_items} />
    </section> : null}

    <section className="dashboard-secondary-grid">
      <article className="dashboard-panel projects-panel"><div className="dashboard-panel-heading"><div><span className="panel-kicker">Recent workspaces</span><h2>Projects</h2></div><a className="panel-link" href="/projects">View all</a></div>{data.latest_projects.length ? <div className="dashboard-project-list">{data.latest_projects.map(project => <a href={`/projects/${project.id}`} className="dashboard-project-row" key={project.id}><div className="project-row-icon">{project.title.slice(0, 1).toUpperCase()}</div><div className="project-row-main"><div className="project-row-heading"><div><strong>{project.title}</strong><span>{project.current_phase || project.project_type || "Project workspace"}</span></div><span className={`project-status status-${project.status.toLowerCase().replace(/\s+/g, "-")}`}>{project.status}</span></div><div className="project-row-progress"><div className="progress-track"><span className="progress-fill" style={{ width: `${project.progress}%` }} /></div><strong>{project.progress}%</strong></div></div></a>)}</div> : <Empty title="No projects yet" text="Create your first workspace to start tracking execution." action="Create project" href="/projects#new-project" />}</article>
      <article className="dashboard-panel deadlines-panel"><div className="dashboard-panel-heading"><div><span className="panel-kicker">Verified next 7 days</span><h2>Upcoming Deadlines</h2></div><a className="panel-link" href="/ask">Ask about deadlines</a></div>{home?.deadlines.items.length ? <div className="deadline-list">{home.deadlines.items.map(item => <DeadlineInsightRow item={item} key={`${item.type}-${item.object_id}-${item.title}`} />)}</div> : data.upcoming_tasks.length ? <div className="deadline-list">{data.upcoming_tasks.map(task => { const d = formatDay(task.deadline); return <a href={task.project ? `/projects/${task.project.id}` : "/tasks"} className="deadline-row" key={task.id}><div className="deadline-date-box"><strong>{d.day}</strong><span>{d.month}</span></div><div className="deadline-main"><h3>{task.title}</h3><p>{scope(task)}</p></div><span className="deadline-status">{task.importance || task.status}</span></a>; })}</div> : <Empty title="No upcoming deadlines" text="LifeOS found no open task or project deadline in the next 7 days." />}</article>
    </section>

    <section className="quick-actions-section"><div className="quick-actions-heading"><div><span className="panel-kicker">Move faster</span><h2>Quick Actions</h2></div><span>{data.counts.notes} notes · {data.counts.documents} documents</span></div><div className="quick-action-grid"><Quick href="/ask" symbol="L" title="Ask LifeOS" text="Review priorities, deadlines, gaps and changes." /><Quick href="/tasks" symbol="✓" title="Open Tasks" text="Review and move your execution queue." /><Quick href="/notes" symbol="N" title="AI Notes" text="Capture context and working knowledge." /><Quick href="/documents" symbol="D" title="Document Brain" text="Upload and question trusted evidence." /></div></section>
  </>;
}

function HomeSignalsCard({ home, completionRate }: { home: HomeIntelligenceData; completionRate: number }) {
  return <div className={`hero-execution-card home-signal-card attention-${home.briefing.attention_level}`}>
    <div className="home-signal-card-heading"><div><span>Today at a glance</span><strong>{home.briefing.headline}</strong></div><span className="home-verified-dot">Verified</span></div>
    <div className="home-signal-grid">{home.briefing.signals.map(signal => <div className={`home-signal signal-${signal.tone}`} key={signal.key}><strong>{signal.count}</strong><span>{signal.label}</span></div>)}</div>
    <div className="home-signal-footer"><span>Execution completion</span><strong>{completionRate}%</strong></div>
  </div>;
}

function TodayIntelligence({ today, onAction, busy }: { today: TodayIntelligenceData; onAction: (priority: TodayPriority, actionType: string) => Promise<void>; busy: boolean }) {
  const priorities = today.priorities.slice(0, 3);
  return <div className="today-intelligence">
    <div className={`today-intelligence-summary attention-${today.attention_level}`}>
      <div><span>Today</span><strong>{today.summary}</strong></div>
      <a href="/ask">Ask LifeOS</a>
    </div>
    {priorities.length ? <div className="today-priority-list">{priorities.map((item, index) => <TodayPriorityCard item={item} rank={index + 1} key={`${item.project_id}-${item.category}-${item.title}`} onAction={onAction} busy={busy} />)}</div> : <div className="today-clear-state"><span>✓</span><div><strong>No ranked attention item right now</strong><p>LifeOS checked your current project state and did not find a concrete blocker, overdue item, near deadline, or stale project signal that outranks your normal work.</p></div></div>}
    <div className="today-intelligence-footer"><span>{today.counts.reviewed_projects} project{today.counts.reviewed_projects === 1 ? "" : "s"} reviewed</span>{today.context_limited ? <span>Context capped by your LifeOS limits</span> : <span>Read-only until you confirm an action</span>}</div>
  </div>;
}

function TodayPriorityCard({ item, rank, onAction, busy }: { item: TodayPriority; rank: number; onAction: (priority: TodayPriority, actionType: string) => Promise<void>; busy: boolean }) {
  return <article className={`today-priority-card severity-${item.severity}`}>
    <div className="today-priority-rank">{rank}</div>
    <div className="today-priority-copy">
      <div className="today-priority-topline"><a href={`/projects/${item.project_id}`}><strong>{item.title}</strong></a><span>{item.project_title}</span></div>
      <p>{item.reason}</p>
      <small><b>Next:</b> {item.recommended_action}</small>
      {item.actions?.length ? <div className="home-priority-actions">{item.actions.slice(0, 2).map(action => <button type="button" disabled={busy} onClick={() => void onAction(item, action.type)} key={action.type}>{action.label}</button>)}</div> : null}
    </div>
    <a className="today-priority-arrow" href={`/projects/${item.project_id}`} aria-label={`Open ${item.project_title}`}>→</a>
  </article>;
}

function HomeActionProposal({ proposal, busy, error, onConfirm, onDismiss }: { proposal: IntelligenceActionProposal; busy: boolean; error: string | null; onConfirm: () => void; onDismiss: () => void }) {
  return <div className={`home-action-proposal status-${proposal.status}`}>
    <div className="home-action-proposal-copy"><span>{proposal.status === "pending" ? "Confirmation required" : proposal.status === "confirmed" ? "Action completed" : proposal.status === "dismissed" ? "Dismissed" : proposal.status === "failed" ? "Action failed" : "Action in progress"}</span><strong>{proposal.title}</strong>{proposal.reason ? <p>{proposal.reason}</p> : null}{proposal.failure_message || error ? <small>{proposal.failure_message || error}</small> : null}</div>
    {proposal.status === "pending" ? <div className="home-action-controls"><button type="button" onClick={onDismiss} disabled={busy}>Dismiss</button><button type="button" className="primary" onClick={onConfirm} disabled={busy}>{busy ? "Working…" : "Confirm action"}</button></div> : null}
  </div>;
}

function HomeInsightCard({ title, kicker, summary, items, empty, href }: { title: string; kicker: string; summary: string; items: HomeInsightItem[]; empty: string; href: string }) {
  return <article className="dashboard-panel home-intelligence-card"><div className="dashboard-panel-heading"><div><span className="panel-kicker">{kicker}</span><h2>{title}</h2></div><a className="panel-link" href={href}>Open</a></div><p className="home-card-summary">{summary}</p>{items.length ? <div className="home-compact-list">{items.map(item => <a href={item.source?.type === "document" && item.source.id ? `/documents/${item.source.id}` : item.project_id ? `/projects/${item.project_id}` : href} key={`${item.type}-${item.object_id}-${item.title}`}><span className={`home-list-dot severity-${item.severity}`} /><div><strong>{item.title}</strong><small>{item.status || item.project_title || item.detail}</small></div><em>→</em></a>)}</div> : <div className="home-mini-empty">✓ {empty}</div>}</article>;
}

function HomeStudyCard({ home }: { home: HomeIntelligenceData }) {
  const items = home.study.items.slice(0, 2);
  return <article className="dashboard-panel home-intelligence-card"><div className="dashboard-panel-heading"><div><span className="panel-kicker">Modules</span><h2>Study Next</h2></div><a className="panel-link" href="/modules">Modules</a></div><p className="home-card-summary">{home.study.summary}</p>{items.length ? <div className="home-compact-list">{items.map(item => <a href={item.module_id ? `/modules/${item.module_id}` : "/modules"} key={`${item.module_id}-${item.object_id}-${item.title}`}><span className={`home-list-dot severity-${item.severity}`} /><div><strong>{item.title}</strong><small>{item.module_title || item.status || "Study item"}</small></div><em>→</em></a>)}</div> : <div className="home-mini-empty">No unfinished lecture is currently ranked.</div>}</article>;
}

function HomeActivityCard({ items, total }: { items: HomeActivityItem[]; total: number }) {
  return <article className="dashboard-panel home-intelligence-card"><div className="dashboard-panel-heading"><div><span className="panel-kicker">I10 activity</span><h2>What Changed Today</h2></div><a className="panel-link" href="/ask">Ask LifeOS</a></div><p className="home-card-summary">{total ? `${total} meaningful change${total === 1 ? "" : "s"} recorded in your workspace today.` : "No meaningful recorded changes yet today."}</p>{items.length ? <div className="home-activity-list">{items.slice(0, 4).map(item => <div key={`${item.event_type}-${item.object_type}-${item.object_id}-${item.occurred_at}`}><span>{compactDateTime(item.occurred_at)}</span><div><strong>{item.title}</strong><small>{item.project_title || item.object_type}</small></div></div>)}</div> : <div className="home-mini-empty">Your recent-change stream is clear.</div>}</article>;
}

function DeadlineInsightRow({ item }: { item: HomeInsightItem }) {
  const d = formatDay(item.deadline);
  const href = item.project_id ? `/projects/${item.project_id}` : item.type === "task" ? "/tasks" : "/projects";
  return <a href={href} className="deadline-row"><div className="deadline-date-box"><strong>{d.day}</strong><span>{d.month}</span></div><div className="deadline-main"><h3>{item.title}</h3><p>{item.project_title || item.detail}</p></div><span className={`deadline-status severity-${item.severity}`}>{item.status || item.severity}</span></a>;
}

function StatCard({ tone, title, value, detail, icon }: { tone: string; title: string; value: number; detail: string; icon: string }) { return <article className={`dashboard-stat-card stat-card-${tone}`}><div className="stat-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d={icon} /></svg></div><div><span>{title}</span><strong>{value}</strong><small>{detail}</small></div></article>; }
function Empty({ title, text, action, href }: { title: string; text: string; action?: string; href?: string }) { return <div className="dashboard-empty-state compact-empty-state"><div className="empty-state-icon">✓</div><h3>{title}</h3><p>{text}</p>{action && href ? <a href={href} className="dashboard-secondary-action compact">{action}</a> : null}</div>; }
function Quick({ href, symbol, title, text }: { href: string; symbol: string; title: string; text: string }) { return <a href={href} className="quick-action-card"><span className="quick-action-icon">{symbol}</span><div><strong>{title}</strong><small>{text}</small></div><em>→</em></a>; }
