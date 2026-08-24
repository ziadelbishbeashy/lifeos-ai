import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { currentPath, navigate } from "../core/navigation";
import { ApiError, apiPost } from "../api/client";
import type { ProjectQuestion, Task } from "../api/types";
import { ProjectForm } from "../features/projects/ProjectForm";
import { deleteProject, fetchProject, projectKeys, updateProject } from "../features/projects/api";
import { TaskForm } from "../features/tasks/TaskForm";
import { createTask, deleteTask, taskKeys, toggleTask, updateTask } from "../features/tasks/api";
import { EmptyState, VerifyButton } from "../components/NativeUi";

export function ProjectDetailsPage() {
  const queryClient = useQueryClient();
  const projectId = Number(currentPath().match(/^\/projects\/(\d+)$/)?.[1] ?? NaN);
  const [editingProject, setEditingProject] = useState(false);
  const [creatingTask, setCreatingTask] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedSuggestions, setSelectedSuggestions] = useState<Set<number>>(new Set());

  const project = useQuery({
    queryKey: projectKeys.detail(projectId),
    queryFn: () => fetchProject(projectId),
    enabled: Number.isFinite(projectId),
  });

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: projectKeys.detail(projectId) }),
      queryClient.invalidateQueries({ queryKey: projectKeys.all }),
      queryClient.invalidateQueries({ queryKey: taskKeys.all }),
      queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
    ]);
  };

  const projectUpdate = useMutation({
    mutationFn: (input: Parameters<typeof updateProject>[1]) => updateProject(projectId, input),
    onSuccess: async () => { setEditingProject(false); setError(null); await refresh(); },
    onError: (failure) => setError(failure instanceof ApiError ? failure.message : "The project could not be updated."),
  });
  const projectDelete = useMutation({
    mutationFn: () => deleteProject(projectId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: projectKeys.all });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      navigate("/projects", true);
    },
  });
  const taskCreate = useMutation({
    mutationFn: createTask,
    onSuccess: async () => { setCreatingTask(false); setError(null); await refresh(); },
    onError: (failure) => setError(failure instanceof ApiError ? failure.message : "The task could not be created."),
  });
  const taskUpdate = useMutation({
    mutationFn: ({ id, input }: { id: number; input: Parameters<typeof updateTask>[1] }) => updateTask(id, input),
    onSuccess: async () => { setEditingTask(null); setError(null); await refresh(); },
    onError: (failure) => setError(failure instanceof ApiError ? failure.message : "The task could not be updated."),
  });
  const taskToggle = useMutation({ mutationFn: toggleTask, onSuccess: refresh });
  const taskDelete = useMutation({ mutationFn: deleteTask, onSuccess: refresh });
  const projectAsk = useMutation({
    mutationFn: (question: string) => apiPost<{ item: ProjectQuestion }>(`/api/v1/projects/${projectId}/questions`, { question }),
    onSuccess: async () => { setError(null); await refresh(); },
    onError: (failure) => setError(failure instanceof ApiError ? failure.message : "LifeOS could not answer from this project's documents."),
  });
  const bulkSuggestions = useMutation({
    mutationFn: (ids: number[]) => apiPost<{ created_count: number; duplicate_count: number; skipped_count: number }>(`/api/v1/projects/${projectId}/document-suggestions/bulk-create`, { suggestion_ids: ids }),
    onSuccess: async () => { setSelectedSuggestions(new Set()); setError(null); await refresh(); },
    onError: (failure) => setError(failure instanceof ApiError ? failure.message : "LifeOS could not create the selected document tasks."),
  });

  function submitProjectQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const question = String(form.get("project_question") || "").trim();
    if (!question) return;
    projectAsk.mutate(question);
    event.currentTarget.reset();
  }

  if (!Number.isFinite(projectId)) return <ProjectState title="Invalid project" text="The project id is not valid." />;
  if (project.isPending) return <ProjectState title="Loading project" text="Building the project workspace…" loading />;
  if (project.isError || !project.data) return <ProjectState title="Project unavailable" text="The project could not be loaded or you do not own it." retry={() => project.refetch()} />;

  const data = project.data;
  const projectsForTask = [{
    id: data.project.id,
    title: data.project.title,
    status: data.project.status,
    priority: data.project.priority,
    progress: data.project.progress,
    deadline: data.project.deadline,
  }];

  return (
    <section className="workspace-page">
      <div className="breadcrumbs"><a href="/projects">Projects</a><span>/</span><strong>{data.project.title}</strong></div>
      <div className="workspace-page-header project-detail-header">
        <div>
          <span className="eyebrow">Project studio</span>
          <h1>{data.project.title}</h1>
          <p>{data.project.goal || data.project.description || "Use this workspace to keep project execution connected to its goal."}</p>
          <div className="chip-row">
            <span className="status-pill">{data.project.status}</span>
            <span className="status-pill">{data.project.priority}</span>
            {data.project_health?.label ? <span className={`health-chip ${data.project_health.tone ?? ""}`}>{data.project_health.label}</span> : null}
          </div>
        </div>
        <div className="header-actions">
          <button className="secondary-button" onClick={() => { setEditingProject((value) => !value); setError(null); }}>{editingProject ? "Close edit" : "Edit project"}</button>
          <button className="danger-button large" onClick={() => { if (window.confirm(`Delete “${data.project.title}”?`)) projectDelete.mutate(); }}>Delete project</button>
        </div>
      </div>

      <div className="summary-strip">
        <Metric label="Task progress" value={`${data.metrics.task_progress}%`} />
        <Metric label="Open tasks" value={data.metrics.total_tasks - data.metrics.completed_tasks} />
        <Metric label="Notes" value={data.metrics.notes_count} />
        <Metric label="Documents" value={data.metrics.document_count} />
      </div>

      {editingProject ? (
        <article className="panel-card workspace-editor">
          <div className="section-heading"><div><span className="panel-kicker">Project settings</span><h2>Edit project</h2></div></div>
          {error ? <div className="form-alert error">{error}</div> : null}
          <ProjectForm
            initial={data.project}
            submitLabel="Save project"
            busy={projectUpdate.isPending}
            onCancel={() => { setEditingProject(false); setError(null); }}
            onSubmit={(input) => projectUpdate.mutateAsync(input).then(() => undefined)}
          />
        </article>
      ) : null}

      <div className="project-detail-grid">
        <article className="panel-card project-info-panel">
          <div className="section-heading"><div><span className="panel-kicker">Project context</span><h2>Overview</h2></div></div>
          <dl className="detail-list">
            <div><dt>Current phase</dt><dd>{data.project.current_phase || "Not set"}</dd></div>
            <div><dt>Type</dt><dd>{data.project.project_type || "Not set"}</dd></div>
            <div><dt>Deadline</dt><dd>{data.project.deadline || "No deadline"}</dd></div>
            <div><dt>Tech stack</dt><dd>{data.project.tech_stack || "Not set"}</dd></div>
          </dl>
          <div className="progress-block"><div><span>Execution progress</span><strong>{data.metrics.task_progress}%</strong></div><div className="progress-track"><span style={{ width: `${data.metrics.task_progress}%` }} /></div></div>
          {data.next_task ? <div className="next-action"><span>Recommended next factual action</span><strong>{data.next_task.title}</strong></div> : null}
        </article>

        <article className="panel-card project-info-panel">
          <div className="section-heading"><div><span className="panel-kicker">Attention</span><h2>Execution signals</h2></div></div>
          <div className="mini-metric-grid two-col">
            <div><span>In progress</span><strong>{data.metrics.in_progress_tasks}</strong></div>
            <div><span>Blocked</span><strong>{data.metrics.blocked_tasks}</strong></div>
            <div><span>Overdue</span><strong>{data.metrics.overdue_tasks}</strong></div>
            <div><span>Due soon</span><strong>{data.metrics.due_soon_tasks}</strong></div>
          </div>
          {data.project_health?.message ? <p className="signal-copy">{data.project_health.message}</p> : null}
        </article>
      </div>

      <article className="panel-card project-section">
        <div className="section-heading">
          <div><span className="panel-kicker">Execution</span><h2>Project tasks</h2></div>
          <button className="primary-button compact" onClick={() => { setCreatingTask((value) => !value); setEditingTask(null); setError(null); }}>{creatingTask ? "Close form" : "+ Add task"}</button>
        </div>

        {(creatingTask || editingTask) ? (
          <div className="nested-editor">
            {error ? <div className="form-alert error">{error}</div> : null}
            <TaskForm
              key={editingTask?.id ?? "project-new"}
              projects={projectsForTask}
              forcedProjectId={projectId}
              initial={editingTask}
              submitLabel={editingTask ? "Save task" : "Create task"}
              busy={taskCreate.isPending || taskUpdate.isPending}
              onCancel={() => { setCreatingTask(false); setEditingTask(null); setError(null); }}
              onSubmit={(input) => editingTask
                ? taskUpdate.mutateAsync({ id: editingTask.id, input }).then(() => undefined)
                : taskCreate.mutateAsync({ ...input, forced_project_id: projectId }).then(() => undefined)}
            />
          </div>
        ) : null}

        <div className="task-table embedded">
          {data.tasks.length ? data.tasks.map((task) => (
            <div className={`task-line ${task.status === "Completed" ? "completed" : ""}`} key={task.id}>
              <button className="complete-button" onClick={() => taskToggle.mutate(task.id)}>{task.status === "Completed" ? "✓" : "○"}</button>
              <div className="task-line-main"><strong>{task.title}</strong><span>{task.module || task.description || "Project task"}</span></div>
              <span className="status-pill">{task.status}</span>
              <span className="importance-pill">{task.importance}</span>
              <span className="task-deadline">{task.deadline || "No deadline"}</span>
              <div className="row-actions"><button className="secondary-button compact" onClick={() => { setEditingTask(task); setCreatingTask(false); setError(null); }}>Edit</button><button className="danger-button" onClick={() => { if (window.confirm(`Delete “${task.title}”?`)) taskDelete.mutate(task.id); }}>Delete</button></div>
            </div>
          )) : <div className="empty-workspace"><strong>No project tasks yet</strong><span>Add the first concrete action for this project.</span></div>}
        </div>
      </article>

      <div className="project-detail-grid">
        <article className="panel-card project-section">
          <div className="section-heading"><div><span className="panel-kicker">Knowledge</span><h2>Recent notes</h2></div><a className="text-link" href="/notes">Open Notes</a></div>
          {data.recent_notes.length ? <div className="simple-resource-list">{data.recent_notes.map((note) => <a href={`/notes/${note.id}`} key={note.id}><strong>{note.is_pinned ? "★ " : ""}{note.title}</strong><span>{note.note_type}</span></a>)}</div> : <div className="empty-workspace compact-empty"><strong>No linked notes</strong><span>Create notes in the Notes workspace and link them to this project.</span></div>}
        </article>

        <article className="panel-card project-section">
          <div className="section-heading"><div><span className="panel-kicker">Evidence</span><h2>Documents</h2></div><a className="text-link" href="/documents">Open Document Brain</a></div>
          {data.documents.length ? <div className="simple-resource-list">{data.documents.map((document) => <a href={`/documents/${document.id}`} key={document.id}><strong>{document.filename}</strong><span>{document.version_label}{document.has_text ? " · searchable" : ""}</span></a>)}</div> : <div className="empty-workspace compact-empty"><strong>No current documents</strong><span>Upload project evidence in Document Brain, then ask grounded questions across the current documents.</span></div>}
        </article>
      </div>


      <article className="panel-card project-section">
        <div className="section-heading"><div><span className="panel-kicker">Document findings</span><h2>Suggested project actions</h2></div><span className="status-pill">{data.pending_document_suggestion_count || 0} pending</span></div>
        <p className="muted-copy">These are grounded actions proposed from linked documents. Select only the ones you want to turn into real tasks.</p>
        {data.document_suggestions?.length ? <div className="details-stack">{data.document_suggestions.map((item) => <div className="resource-row" key={item.id}><label className="check-row"><input type="checkbox" disabled={item.status !== "Pending"} checked={selectedSuggestions.has(item.id)} onChange={(event) => setSelectedSuggestions((current) => { const next = new Set(current); event.target.checked ? next.add(item.id) : next.delete(item.id); return next; })} /><span><strong>{item.title}</strong><small>{item.priority} · {item.lifecycle_label}</small></span></label><VerifyButton source={item.source as any} /></div>)}</div> : <EmptyState title="No document-derived actions" text="Analyze linked documents to surface grounded task suggestions here." />}
        {selectedSuggestions.size ? <div className="form-actions"><button className="primary-button" disabled={bulkSuggestions.isPending} onClick={() => bulkSuggestions.mutate([...selectedSuggestions])}>{bulkSuggestions.isPending ? "Creating…" : `Create ${selectedSuggestions.size} task${selectedSuggestions.size === 1 ? "" : "s"}`}</button></div> : null}
      </article>

      <article className="panel-card project-section">
        <div className="section-heading"><div><span className="panel-kicker">Project RAG</span><h2>Ask across project documents</h2></div><span className="status-pill">{data.metrics.searchable_document_count} searchable</span></div>
        <p className="muted-copy">Answers use the current readable documents linked to this project. Sources stay available through the small Verify controls.</p>
        {error ? <div className="form-alert error">{error}</div> : null}
        <form className="ask-row" onSubmit={submitProjectQuestion}>
          <input name="project_question" placeholder="What do the current project documents say about…?" maxLength={2000} />
          <button className="primary-button" disabled={projectAsk.isPending || data.metrics.searchable_document_count === 0}>{projectAsk.isPending ? "Searching…" : "Ask project"}</button>
        </form>
        <div className="ask-history">
          {data.project_question_history?.length ? data.project_question_history.map((item) => (
            <article className="ask-entry" key={item.id}>
              <div className="question">{item.question}</div>
              <div className="answer">{item.answer || item.error_message || "No saved answer."}</div>
              {item.sources?.length ? <div className="qa-sources">{item.sources.slice(0, 5).map((source, index) => <VerifyButton key={index} source={source as any} label={`Source ${index + 1}`} />)}</div> : null}
            </article>
          )) : <EmptyState title="No project questions yet" text="Ask across the project's current documents when you need a cross-file answer." />}
        </div>
      </article>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) { return <div><span>{label}</span><strong>{value}</strong></div>; }
function ProjectState({ title, text, loading, retry }: { title: string; text: string; loading?: boolean; retry?: () => void }) {
  return <section><div className={`page-state panel-card ${!loading ? "error-state" : ""}`}>{loading ? <div className="spinner" /> : null}<div><strong>{title}</strong><span>{text}</span></div>{retry ? <button className="secondary-button" onClick={retry}>Try again</button> : null}</div></section>;
}
