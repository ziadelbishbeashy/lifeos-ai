import { useQuery } from "@tanstack/react-query";
import type { CSSProperties } from "react";
import { apiGet } from "../api/client";
import type { DashboardData, DashboardTask } from "../api/types";
import { useSession } from "../auth/session";

function formatDay(value: string | null) {
  if (!value) return { day: "--", month: "---" };
  const date = new Date(`${value}T00:00:00`);
  return { day: String(date.getDate()).padStart(2,"0"), month: date.toLocaleString(undefined,{month:"short"}) };
}
function scope(task: DashboardTask) { return task.project?.title || "General Workspace"; }
function progressStyle(value: number): CSSProperties { return { ["--progress" as string]: value } as CSSProperties; }

export function DashboardPage() {
  const session = useSession();
  const query = useQuery({ queryKey:["dashboard"], queryFn:()=>apiGet<DashboardData>("/api/v1/dashboard") });
  if (query.isPending) return <div className="dashboard-empty-state"><div className="empty-state-icon">…</div><h3>Opening dashboard</h3><p>Loading your workspace overview…</p></div>;
  if (query.isError || !query.data) return <div className="dashboard-empty-state"><div className="empty-state-icon">!</div><h3>Dashboard unavailable</h3><p>LifeOS could not load your workspace data.</p><button className="dashboard-secondary-action compact" onClick={()=>query.refetch()}>Try again</button></div>;
  const data = query.data;
  const firstName = session.data?.user?.name?.split(/\s+/)[0] || "there";
  const overdue = data.counts.overdue_tasks;

  return <>
    <section className="dashboard-hero">
      <div className="dashboard-hero-copy">
        <span className="dashboard-eyebrow">Welcome back, {firstName}</span>
        <h1>Turn today into <span>measurable progress.</span></h1>
        <p>Your projects, tasks and execution signals are gathered here so you can focus on the next meaningful action.</p>
        <div className="dashboard-hero-actions"><a href="/projects#new-project" className="dashboard-primary-action"><span>+</span>Create Project</a><a href="/projects" className="dashboard-secondary-action">View Workspace</a></div>
      </div>
      <div className="hero-execution-card">
        <div className="execution-card-heading"><div><span>Execution readiness</span><strong>{data.completion_rate}%</strong></div><div className="mini-progress-ring" style={progressStyle(data.completion_rate)} aria-label={`${data.completion_rate} percent task completion`}><span/></div></div>
        <div className="execution-card-metrics"><div><span>Active projects</span><strong>{data.counts.active_projects}</strong></div><div><span>Open actions</span><strong>{data.counts.open_tasks}</strong></div><div><span>Average progress</span><strong>{data.average_project_progress}%</strong></div></div>
        <p>{overdue ? `${overdue} overdue task${overdue===1?"":"s"} need attention.` : data.counts.open_tasks ? "Your workspace is clear of overdue work." : "Add tasks to begin measuring execution health."}</p>
      </div>
    </section>

    <section className="dashboard-stat-grid" aria-label="Workspace statistics">
      <StatCard tone="purple" title="Active Projects" value={data.counts.active_projects} detail={`${data.counts.projects} total workspaces`} icon="M3 6.5A2.5 2.5 0 0 1 5.5 4H9l2 2h7.5A2.5 2.5 0 0 1 21 8.5v8A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5v-10Z"/>
      <StatCard tone="blue" title="Open Tasks" value={data.counts.open_tasks} detail={`${data.counts.tasks} total actions`} icon="M9 5h11v2H9V5Zm0 6h11v2H9v-2Zm0 6h11v2H9v-2ZM4.5 4A1.5 1.5 0 1 1 3 5.5 1.5 1.5 0 0 1 4.5 4Zm0 6A1.5 1.5 0 1 1 3 11.5 1.5 1.5 0 0 1 4.5 10Zm0 6A1.5 1.5 0 1 1 3 17.5 1.5 1.5 0 0 1 4.5 16Z"/>
      <StatCard tone="green" title="Completed" value={data.counts.completed_tasks} detail={`${data.completion_rate}% completion rate`} icon="m9.5 16.2-3.7-3.7L4.4 14l5.1 5.1L20 8.6 18.6 7.2 9.5 16.2Z"/>
      <StatCard tone="red" title="Blocked Tasks" value={data.counts.blocked_tasks} detail={`${data.counts.overdue_tasks} overdue`} icon="M11 7h2v6h-2V7Zm0 8h2v2h-2v-2Zm1-13 10 18H2L12 2Zm0 4.1L5.4 18h13.2L12 6.1Z"/>
    </section>

    <section className="dashboard-main-grid">
      <article className="dashboard-panel focus-panel">
        <div className="dashboard-panel-heading"><div><span className="panel-kicker">Smart focus</span><h2>Today's Priority</h2></div><span className="live-status"><i/>Live</span></div>
        {data.focus_task ? <div className="focus-task-card"><div className="focus-task-topline"><span className={`focus-importance importance-${(data.focus_task.importance||"medium").toLowerCase()}`}>{data.focus_task.importance||"Medium"} priority</span><span className="focus-status">{data.focus_task.status}</span></div><h3>{data.focus_task.title}</h3><p>{data.focus_task.description || "This action has been selected from your active work based on status, importance and deadline."}</p><div className="focus-task-meta"><span><small>Scope</small><strong>{scope(data.focus_task)}</strong></span><span><small>Module</small><strong>{data.focus_task.module||"General"}</strong></span><span><small>Deadline</small><strong>{data.focus_task.deadline||"No deadline"}</strong></span></div><div className="focus-task-actions"><a href={data.focus_task.project?`/projects/${data.focus_task.project.id}`:"/tasks"} className="dashboard-primary-action compact">{data.focus_task.project?"Open Project":"Open Task Center"}</a><a href="/tasks" className="dashboard-secondary-action compact">Edit Task</a></div></div> : <Empty title="No active priority task" text="Add a task or reopen an existing one to create your next focus." action="Open Projects" href="/projects"/>}
      </article>

      <article className="dashboard-panel health-panel">
        <div className="dashboard-panel-heading"><div><span className="panel-kicker">Workspace signal</span><h2>Execution Health</h2></div></div>
        <div className="health-ring-layout"><div className="progress-ring" style={progressStyle(data.completion_rate)}><div className="progress-ring-inner"><strong>{data.completion_rate}%</strong><span>complete</span></div></div><div className="health-breakdown"><div><span><i className="health-dot completed-dot"/>Completed</span><strong>{data.counts.completed_tasks}</strong></div><div><span><i className="health-dot open-dot"/>Open</span><strong>{data.counts.open_tasks}</strong></div><div><span><i className="health-dot blocked-dot"/>Blocked</span><strong>{data.counts.blocked_tasks}</strong></div><p className="health-message">{overdue ? `${overdue} overdue task${overdue===1?"":"s"} need attention.` : "No overdue tasks right now."}</p></div></div>
      </article>
    </section>

    <section className="dashboard-secondary-grid">
      <article className="dashboard-panel projects-panel"><div className="dashboard-panel-heading"><div><span className="panel-kicker">Recent workspaces</span><h2>Projects</h2></div><a className="panel-link" href="/projects">View all</a></div>{data.latest_projects.length?<div className="dashboard-project-list">{data.latest_projects.map(project=><a href={`/projects/${project.id}`} className="dashboard-project-row" key={project.id}><div className="project-row-icon">{project.title.slice(0,1).toUpperCase()}</div><div className="project-row-main"><div className="project-row-heading"><div><strong>{project.title}</strong><span>{project.current_phase||project.project_type||"Project workspace"}</span></div><span className={`project-status status-${project.status.toLowerCase().replace(/\s+/g,"-")}`}>{project.status}</span></div><div className="project-row-progress"><div className="progress-track"><span className="progress-fill" style={{width:`${project.progress}%`}}/></div><strong>{project.progress}%</strong></div></div></a>)}</div>:<Empty title="No projects yet" text="Create your first workspace to start tracking execution." action="Create project" href="/projects#new-project"/>}</article>
      <article className="dashboard-panel deadlines-panel"><div className="dashboard-panel-heading"><div><span className="panel-kicker">Time-sensitive work</span><h2>Upcoming Deadlines</h2></div><span className="panel-date">{new Date(data.today+"T00:00:00").toLocaleDateString(undefined,{month:"short",day:"numeric"})}</span></div>{data.upcoming_tasks.length?<div className="deadline-list">{data.upcoming_tasks.map(task=>{const d=formatDay(task.deadline);return <a href={task.project?`/projects/${task.project.id}`:"/tasks"} className="deadline-row" key={task.id}><div className="deadline-date-box"><strong>{d.day}</strong><span>{d.month}</span></div><div className="deadline-main"><h3>{task.title}</h3><p>{scope(task)}</p></div><span className="deadline-status">{task.importance||task.status}</span></a>})}</div>:<Empty title="No upcoming deadlines" text="Your current task list has no dated deadlines."/>}</article>
    </section>

    <section className="quick-actions-section"><div className="quick-actions-heading"><div><span className="panel-kicker">Move faster</span><h2>Quick Actions</h2></div><span>{data.counts.notes} notes · {data.counts.documents} documents</span></div><div className="quick-action-grid"><Quick href="/projects#new-project" symbol="+" title="Create Project" text="Start a new goal-driven workspace."/><Quick href="/tasks" symbol="✓" title="Open Tasks" text="Review and move your execution queue."/><Quick href="/notes" symbol="N" title="AI Notes" text="Capture context and working knowledge."/><Quick href="/documents" symbol="D" title="Document Brain" text="Upload and question trusted evidence."/></div></section>
  </>;
}

function StatCard({tone,title,value,detail,icon}:{tone:string;title:string;value:number;detail:string;icon:string}) { return <article className={`dashboard-stat-card stat-card-${tone}`}><div className="stat-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d={icon}/></svg></div><div><span>{title}</span><strong>{value}</strong><small>{detail}</small></div></article>; }
function Empty({title,text,action,href}:{title:string;text:string;action?:string;href?:string}) { return <div className="dashboard-empty-state compact-empty-state"><div className="empty-state-icon">✓</div><h3>{title}</h3><p>{text}</p>{action&&href?<a href={href} className="dashboard-secondary-action compact">{action}</a>:null}</div>; }
function Quick({href,symbol,title,text}:{href:string;symbol:string;title:string;text:string}) { return <a href={href} className="quick-action-card"><span className="quick-action-icon">{symbol}</span><div><strong>{title}</strong><small>{text}</small></div><em>→</em></a>; }
