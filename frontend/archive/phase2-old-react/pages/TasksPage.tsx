import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import type { Task } from "../api/types";
import { TaskForm } from "../features/tasks/TaskForm";
import { createTask, deleteTask, fetchTasks, taskKeys, toggleTask, updateTask } from "../features/tasks/api";
import { projectKeys } from "../features/projects/api";

export function TasksPage() {
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Task | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [scopeFilter, setScopeFilter] = useState("all");
  const [error, setError] = useState<string | null>(null);

  const tasks = useQuery({ queryKey: taskKeys.all, queryFn: fetchTasks });

  const refresh = async (projectId?: number | null) => {
    const promises = [
      queryClient.invalidateQueries({ queryKey: taskKeys.all }),
      queryClient.invalidateQueries({ queryKey: projectKeys.all }),
      queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
    ];
    if (projectId) promises.push(queryClient.invalidateQueries({ queryKey: projectKeys.detail(projectId) }));
    await Promise.all(promises);
  };

  const createMutation = useMutation({
    mutationFn: createTask,
    onSuccess: async (result) => { setCreating(false); setError(null); await refresh(result.item.project_id); },
    onError: (failure) => setError(failure instanceof ApiError ? failure.message : "The task could not be created."),
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, input }: { id: number; input: Parameters<typeof updateTask>[1] }) => updateTask(id, input),
    onSuccess: async (result) => { setEditing(null); setError(null); await refresh(result.item.project_id); },
    onError: (failure) => setError(failure instanceof ApiError ? failure.message : "The task could not be updated."),
  });
  const toggleMutation = useMutation({ mutationFn: toggleTask, onSuccess: (result) => refresh(result.item.project_id) });
  const deleteMutation = useMutation({ mutationFn: deleteTask, onSuccess: (result) => refresh(result.project_id) });

  const filtered = useMemo(() => {
    if (!tasks.data) return [];
    return tasks.data.items.filter((task) => {
      if (statusFilter !== "all" && task.status !== statusFilter) return false;
      if (scopeFilter === "general" && task.project_id !== null) return false;
      if (scopeFilter === "project" && task.project_id === null) return false;
      return true;
    });
  }, [tasks.data, statusFilter, scopeFilter]);

  if (tasks.isPending) return <TaskPageState text="Loading task workspace…" />;
  if (tasks.isError || !tasks.data) return <TaskPageState text="Task API unavailable." error retry={() => tasks.refetch()} />;

  const data = tasks.data;
  return (
    <section className="workspace-page">
      <div className="workspace-page-header">
        <div><span className="eyebrow">Execution center</span><h1>Tasks</h1><p>Manage general and project work through the same task service that powers the legacy application.</p></div>
        <button className="primary-button" onClick={() => { setCreating((value) => !value); setEditing(null); setError(null); }}>{creating ? "Close form" : "+ Add Task"}</button>
      </div>

      <div className="summary-strip">
        <Summary label="All" value={data.counts.total} />
        <Summary label="In progress" value={data.counts.in_progress} />
        <Summary label="Blocked" value={data.counts.blocked} />
        <Summary label="Overdue" value={data.counts.overdue} />
      </div>

      {(creating || editing) ? (
        <article className="panel-card workspace-editor">
          <div className="section-heading"><div><span className="panel-kicker">Task editor</span><h2>{editing ? "Edit task" : "Create task"}</h2></div></div>
          {error ? <div className="form-alert error">{error}</div> : null}
          <TaskForm
            key={editing?.id ?? "new"}
            projects={data.projects}
            initial={editing}
            submitLabel={editing ? "Save changes" : "Create task"}
            busy={createMutation.isPending || updateMutation.isPending}
            onCancel={() => { setCreating(false); setEditing(null); setError(null); }}
            onSubmit={(input) => editing
              ? updateMutation.mutateAsync({ id: editing.id, input }).then(() => undefined)
              : createMutation.mutateAsync(input).then(() => undefined)}
          />
        </article>
      ) : null}

      <div className="filter-bar panel-card">
        <label><span>Status</span><select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}><option value="all">All statuses</option><option>Pending</option><option>In Progress</option><option>Blocked</option><option>Completed</option></select></label>
        <label><span>Scope</span><select value={scopeFilter} onChange={(e) => setScopeFilter(e.target.value)}><option value="all">All work</option><option value="general">General</option><option value="project">Project tasks</option></select></label>
        <span className="filter-count">{filtered.length} shown</span>
      </div>

      <div className="task-table panel-card">
        {filtered.length ? filtered.map((task) => (
          <div className={`task-line ${task.status === "Completed" ? "completed" : ""}`} key={task.id}>
            <button className="complete-button" title="Toggle completion" onClick={() => toggleMutation.mutate(task.id)}>{task.status === "Completed" ? "✓" : "○"}</button>
            <div className="task-line-main">
              <strong>{task.title}</strong>
              <span>{task.project ? <Link to={`/projects/${task.project.id}`}>{task.project.title}</Link> : "General workspace"}{task.module ? ` · ${task.module}` : ""}</span>
            </div>
            <span className="status-pill">{task.status}</span>
            <span className="importance-pill">{task.importance}</span>
            <span className="task-deadline">{task.deadline || "No deadline"}</span>
            <div className="row-actions">
              <button className="secondary-button compact" onClick={() => { setEditing(task); setCreating(false); setError(null); }}>Edit</button>
              <button className="danger-button" onClick={() => { if (window.confirm(`Delete “${task.title}”?`)) deleteMutation.mutate(task.id); }}>Delete</button>
            </div>
          </div>
        )) : <div className="empty-workspace"><strong>No tasks match these filters</strong><span>Change the filters or create a task.</span></div>}
      </div>
    </section>
  );
}

function Summary({ label, value }: { label: string; value: number }) { return <div><span>{label}</span><strong>{value}</strong></div>; }
function TaskPageState({ text, error, retry }: { text: string; error?: boolean; retry?: () => void }) {
  return <section><div className={`page-state panel-card ${error ? "error-state" : ""}`}>{!error ? <div className="spinner" /> : null}<div><strong>{error ? "Tasks unavailable" : "Loading"}</strong><span>{text}</span></div>{retry ? <button className="secondary-button" onClick={retry}>Try again</button> : null}</div></section>;
}
