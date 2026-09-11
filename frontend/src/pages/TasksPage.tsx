import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../api/client";
import type { Task, TaskInput } from "../api/types";
import { TaskForm } from "../features/tasks/TaskForm";
import { createTask, deleteTask, fetchTasks, taskKeys, toggleTask, updateTask } from "../features/tasks/api";
import { projectKeys } from "../features/projects/api";
import { Icon, Modal, PageSkeleton } from "../components/VSpaceUi";
import { PageState } from "../components/NativeUi";

type View = "all" | "today" | "upcoming" | "overdue" | "completed";
const views: { key: View; label: string }[] = [{ key: "all", label: "My Tasks" }, { key: "today", label: "Today" }, { key: "upcoming", label: "Upcoming" }, { key: "overdue", label: "Overdue" }, { key: "completed", label: "Completed" }];
const slug = (value: string) => value.toLowerCase().replace(/\s+/g, "-");
function localDay() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`; }
function inView(task: Task, view: View, today: string) {
  if (view === "completed") return task.status === "Completed";
  if (view === "all") return true;
  if (task.status === "Completed" || !task.deadline) return false;
  if (view === "today") return task.deadline === today;
  return view === "upcoming" ? task.deadline > today : task.deadline < today;
}
export function TasksPage() {
  const qc = useQueryClient();
  const [creating, setCreating] = useState(() => window.location.hash === "#new-task");
  const [editing, setEditing] = useState<Task | null>(null);
  const [search, setSearch] = useState("");
  const [view, setView] = useState<View>(() => { const value = new URLSearchParams(location.search).get("view"); return views.find(v => v.key === value)?.key || "all"; });
  const [status, setStatus] = useState("all"), [importance, setImportance] = useState("all"), [scope, setScope] = useState("all"), [project, setProject] = useState("all");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const openedLink = useRef(false);
  const q = useQuery({ queryKey: taskKeys.all, queryFn: fetchTasks });
  const today = localDay();
  useEffect(() => {
    if (!q.data || openedLink.current) return;
    openedLink.current = true;
    const id = Number(new URLSearchParams(location.search).get("task"));
    if (id) setEditing(q.data.items.find(t => t.id === id) || null);
  }, [q.data]);
  async function refresh(id?: number | null) {
    await Promise.all([qc.invalidateQueries({ queryKey: taskKeys.all }), qc.invalidateQueries({ queryKey: projectKeys.all }), qc.invalidateQueries({ queryKey: ["dashboard"] }), qc.invalidateQueries({ queryKey: ["vspace", "command-index"] }), ...(id ? [qc.invalidateQueries({ queryKey: projectKeys.detail(id) })] : [])]);
  }
  function close() { setCreating(false); setEditing(null); setError(null); history.replaceState(null, "", "/tasks"); }
  function fail(e: Error) { setError(e instanceof ApiError ? e.message : "We couldn’t save this change. Please try again."); }
  const create = useMutation({ mutationFn: createTask, onSuccess: async r => { close(); setNotice("Task created."); await refresh(r.item.project_id); }, onError: fail });
  const update = useMutation({ mutationFn: ({ id, input }: { id: number; input: TaskInput }) => updateTask(id, input), onSuccess: async r => { close(); setNotice("Task updated."); await refresh(r.item.project_id); }, onError: fail });
  const toggle = useMutation({ mutationFn: toggleTask, onSuccess: async r => { setError(null); setNotice(r.message || "Task updated."); await refresh(r.item.project_id); }, onError: fail });
  const del = useMutation({ mutationFn: deleteTask, onSuccess: async r => { setError(null); setNotice("Task deleted."); await refresh(r.project_id); }, onError: fail });
  const filtered = useMemo(() => (q.data?.items || []).filter(t => {
    const haystack = [t.title, t.description, t.module, t.tags, t.project?.title].filter(Boolean).join(" ").toLowerCase();
    return inView(t, view, today) && (!search.trim() || haystack.includes(search.trim().toLowerCase()))
      && (status === "all" || (status === "recurring" ? t.is_recurring : t.status.toLowerCase() === status))
      && (importance === "all" || t.importance.toLowerCase() === importance)
      && (scope === "all" || (scope === "general" ? t.project_id === null : t.project_id !== null))
      && (project === "all" || (project === "general" ? t.project_id === null : String(t.project_id) === project));
  }), [q.data, view, search, status, importance, scope, project, today]);
  function reset() { setSearch(""); setStatus("all"); setImportance("all"); setScope("all"); setProject("all"); }
  if (q.isPending) return <PageSkeleton label="Loading your tasks…"/>;
  if (q.isError || !q.data) return <PageState title="Tasks unavailable" text="We couldn’t load your tasks. Please try again." error retry={() => void q.refetch()}/>;
  const data = q.data, busy = create.isPending || update.isPending;
  return <div className="task-center-page vs-tasks-page">
    <header className="workspace-page-header"><div><span className="workspace-eyebrow">A little progress, every day</span><h1>Tasks</h1><p>Make room for the work that matters.</p></div><button type="button" className="workspace-primary-button" onClick={() => { setCreating(true); setEditing(null); setError(null); }}><Icon name="plus"/>New Task</button></header>
    <div className="vs-task-summary"><span><strong>{data.counts.in_progress}</strong> in progress</span><span><strong>{data.counts.general}</strong> general</span><span><strong>{data.counts.project}</strong> in projects</span><span className={data.counts.overdue ? "vs-warning-text" : ""}><strong>{data.counts.overdue}</strong> overdue</span></div>
    <nav className="vs-view-tabs" aria-label="Task views">{views.map(v => <button type="button" key={v.key} className={view === v.key ? "active" : ""} aria-pressed={view === v.key} onClick={() => setView(v.key)}>{v.label}<span>{data.items.filter(t => inView(t, v.key, today)).length}</span></button>)}</nav>
    <section className="task-filter-panel"><div className="task-search-wrapper"><Icon name="search"/><input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search all tasks…" aria-label="Search tasks"/></div><select aria-label="Filter by status" value={status} onChange={e => setStatus(e.target.value)}><option value="all">All statuses</option><option value="recurring">Recurring</option><option value="pending">Pending</option><option value="in progress">In Progress</option><option value="blocked">Blocked</option><option value="completed">Completed</option></select><select aria-label="Filter by priority" value={importance} onChange={e => setImportance(e.target.value)}><option value="all">All priorities</option>{["Low","Medium","High","Critical"].map(x => <option key={x} value={x.toLowerCase()}>{x}</option>)}</select><select aria-label="Filter by scope" value={scope} onChange={e => setScope(e.target.value)}><option value="all">All scopes</option><option value="general">General workspace</option><option value="project">Project tasks</option></select><select aria-label="Filter by project" value={project} onChange={e => setProject(e.target.value)}><option value="all">All projects</option><option value="general">General Workspace</option>{data.projects.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}</select><button type="button" className="clear-task-filters" onClick={reset}>Clear</button></section>
    {error && !editing && !creating ? <div className="form-alert error" role="alert">{error}</div> : null}{notice ? <div className="vs-inline-notice" role="status">{notice}<button type="button" onClick={() => setNotice(null)} aria-label="Dismiss notification"><Icon name="close"/></button></div> : null}
    {filtered.length ? <section className="professional-task-list" aria-label="Tasks">{filtered.map(t => <article key={t.id} className={`professional-task-card ${t.status === "Completed" ? "completed" : ""} ${t.deadline && t.deadline < today && t.status !== "Completed" ? "overdue" : ""}`}>
      <button type="button" className={`professional-task-toggle ${t.status === "Completed" ? "checked" : ""}`} aria-label={`${t.status === "Completed" ? "Reopen" : "Complete"} ${t.title}`} aria-pressed={t.status === "Completed"} disabled={toggle.isPending} onClick={() => toggle.mutate(t.id)}>{t.status === "Completed" ? <Icon name="check"/> : null}</button>
      <div className="professional-task-content"><h3><button type="button" className="vs-task-title" onClick={() => { setEditing(t); setCreating(false); setError(null); }}>{t.title}</button></h3><div className="professional-task-labels"><span className={`task-scope-badge ${t.project_id ? "task-scope-project" : "task-scope-general"}`}>{t.project?.title || "General Workspace"}</span><span className={`task-importance-label importance-${t.importance.toLowerCase()}`}>{t.importance}</span><span className={`task-status-label status-${slug(t.status)}`}>{t.status}</span>{t.deadline ? <span className="task-deadline-label"><Icon name="calendar"/>{t.deadline === today ? "Today" : new Date(`${t.deadline}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" })}</span> : null}{t.module ? <span className="task-module-label">{t.module}</span> : null}{t.reminder_enabled ? <span className="task-reminder-label">Reminder</span> : null}{t.is_recurring ? <span className="task-recurring-label">Recurring</span> : null}</div>{t.description ? <p className="professional-task-description">{t.description}</p> : null}<div className="professional-task-meta"><span>Difficulty <strong>{t.difficulty}</strong></span>{t.tags ? <span>Tags <strong>{t.tags}</strong></span> : null}</div></div>
      <div className="professional-task-actions"><button type="button" className="task-edit-action" onClick={() => { setEditing(t); setCreating(false); setError(null); }}>Edit</button><button type="button" className="task-edit-action task-action-muted" disabled={del.isPending} onClick={() => { if (confirm(`Delete “${t.title}”?`)) del.mutate(t.id); }}>Delete</button></div>
    </article>)}</section> : <div className="professional-task-empty-state"><span className="empty-task-symbol"><Icon name="tasks"/></span><h3>{data.items.length ? "A clear view." : "Your next step starts here."}</h3><p>{data.items.length ? "No tasks match this view and its filters." : "Capture a task, set its priority, and give it a place in your day."}</p><button type="button" className="workspace-primary-button" onClick={() => setCreating(true)}>Create task</button>{data.items.length ? <button type="button" className="workspace-secondary-button" onClick={() => { reset(); setView("all"); }}>Show all tasks</button> : null}</div>}
    {creating || editing ? <Modal title={editing ? "Edit Task" : "New Task"} drawer busy={busy} onClose={close}>
      {error ? <div className="form-alert error" role="alert">{error}</div> : null}<TaskForm key={editing?.id || "new"} projects={data.projects} initial={editing} submitLabel={editing ? "Save changes" : "Create task"} busy={busy} onCancel={close} onSubmit={input => { if (editing) update.mutate({ id: editing.id, input }); else create.mutate(input); }}/>
    </Modal> : null}
  </div>;
}
