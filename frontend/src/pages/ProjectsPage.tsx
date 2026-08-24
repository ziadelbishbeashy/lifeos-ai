import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ApiError } from "../api/client";
import type { ProjectCard, ProjectInput } from "../api/types";
import { EmptyState, ErrorBanner, PageHeader, PageState, Stat } from "../components/NativeUi";
import { ProjectForm } from "../features/projects/ProjectForm";
import { createProject, fetchProjects, projectKeys } from "../features/projects/api";

function formatDate(value: string | null, withYear = true) {
  if (!value) return "";
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(year, (month || 1) - 1, day || 1);
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    ...(withYear ? { year: "numeric" as const } : {}),
  }).format(date);
}

function truncate(value: string, max = 170) {
  if (value.length <= max) return value;
  const candidate = value.slice(0, Math.max(0, max - 3));
  const boundary = candidate.lastIndexOf(" ");
  return `${(boundary > candidate.length * 0.6 ? candidate.slice(0, boundary) : candidate).trimEnd()}...`;
}

function slug(value: string) { return value.toLowerCase().replace(/\s+/g, "-"); }

function ProjectCardView({ card }: { card: ProjectCard }) {
  const summary = card.goal || card.description || "No project goal has been added yet.";
  const healthTone = card.health?.tone || "neutral";
  const healthLabel = card.health?.label || "On track";
  const healthMessage = card.health?.message || "No urgent project signal detected.";
  const status = card.status || "In Progress";
  const priority = card.priority || "Medium";
  return (
    <article className="project-studio-card">
      <div className="project-studio-card-topline">
        <div className="project-studio-card-identity"><span className="project-studio-avatar">{card.title.charAt(0).toUpperCase()}</span><div><span className="workspace-eyebrow">{card.project_type || "Project"}</span><h3>{card.title}</h3></div></div>
        <span className={`project-health-pill project-health-${healthTone}`}>{healthLabel}</span>
      </div>
      <p className="project-studio-card-summary">{truncate(summary)}</p>
      <div className="project-studio-progress-row"><div><span>Execution progress</span><strong>{card.task_progress}%</strong></div><div className="professional-progress-track"><div className="professional-progress-fill" style={{ width: `${card.task_progress}%` }} /></div></div>
      <div className="project-studio-signal-row"><span><strong>{card.open_tasks}</strong> open tasks</span><span><strong>{card.note_count}</strong> notes</span>{card.deadline ? <span>Due {formatDate(card.deadline)}</span> : <span>No project deadline</span>}</div>
      <div className="project-studio-health-copy"><span>Current signal</span><p>{healthMessage}</p></div>
      <div className="project-studio-next-action"><span>Next action</span>{card.next_task ? <><strong>{card.next_task.title}</strong><small>{card.next_task.status} · {card.next_task.importance || "Medium"} priority{card.next_task.deadline ? ` · Due ${formatDate(card.next_task.deadline, false)}` : ""}</small></> : <><strong>{status === "Completed" ? "Project complete" : "Add the first actionable task"}</strong><small>{status === "Completed" ? "No unfinished tasks remain." : "Turn the project goal into a clear next step."}</small></>}</div>
      <div className="project-studio-card-footer"><div className="project-studio-badges"><span className={`project-status-badge project-status-${slug(status)}`}>{status}</span><span className={`project-priority-badge project-priority-${priority.toLowerCase()}`}>{priority}</span></div><a href={`/projects/${card.id}`} className="workspace-primary-button project-studio-open-button">Open Project</a></div>
    </article>
  );
}

export function ProjectsPage() {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [priority, setPriority] = useState("all");
  const [error, setError] = useState<string | null>(null);
  const projects = useQuery({ queryKey: projectKeys.all, queryFn: fetchProjects, retry: false });
  const createMutation = useMutation({
    mutationFn: createProject,
    onSuccess: async () => {
      setCreateOpen(false); setError(null);
      await Promise.all([queryClient.invalidateQueries({ queryKey: projectKeys.all }), queryClient.invalidateQueries({ queryKey: ["dashboard"] })]);
    },
    onError: (failure) => setError(failure instanceof ApiError ? failure.message : "The project could not be created."),
  });

  const filtered = useMemo(() => {
    const items = projects.data?.items ?? [];
    const needle = search.trim().toLowerCase();
    return items.filter((card) => {
      const haystack = [card.title, card.goal, card.description, card.tech_stack, card.current_phase, card.project_type].filter(Boolean).join(" ").toLowerCase();
      return (!needle || haystack.includes(needle)) && (status === "all" || card.status.toLowerCase() === status) && (priority === "all" || card.priority.toLowerCase() === priority);
    });
  }, [projects.data?.items, search, status, priority]);

  if (projects.isPending) return <PageState title="Opening projects" text="Loading your project workspace…" />;
  if (projects.isError || !projects.data) return <PageState title="Projects unavailable" text="LifeOS could not load your projects." error retry={() => projects.refetch()} />;
  const data = projects.data;

  async function submitProject(input: ProjectInput) { await createMutation.mutateAsync(input); }
  function clearFilters() { setSearch(""); setStatus("all"); setPriority("all"); }

  return (
    <section className="workspace-page project-studio-index">
      <PageHeader eyebrow="Project workspace" title="Keep every project moving." description="See what needs attention, continue the right task, and keep notes and execution connected without opening every project." actions={<button type="button" className="workspace-primary-button" onClick={() => { setCreateOpen(true); setError(null); }}>+ New Project</button>} />
      <div className="summary-strip"><Stat label="Active projects" value={data.counts.active} hint="Currently moving" /><Stat label="Need attention" value={data.counts.attention} hint="Blocked, overdue, or close" /><Stat label="Completed" value={data.counts.completed} hint="Finished workspaces" /></div>
      <ErrorBanner message={error} />

      {createOpen ? <article className="panel-card workspace-editor"><div className="section-heading"><div><span className="panel-kicker">New workspace</span><h2>Create project</h2></div><button className="secondary-button compact" onClick={() => setCreateOpen(false)}>Close</button></div><ProjectForm submitLabel="Create project" busy={createMutation.isPending} onSubmit={submitProject} onCancel={() => setCreateOpen(false)} /></article> : null}

      {data.items.length ? <>
        <section className="project-filter-panel project-studio-filter"><div className="project-search-wrapper"><span className="project-search-icon">⌕</span><input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search projects, goals, technologies, or phases…" /></div><div className="project-filter-controls"><select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status"><option value="all">All statuses</option><option value="planning">Planning</option><option value="in progress">In Progress</option><option value="paused">Paused</option><option value="completed">Completed</option></select><select value={priority} onChange={(e) => setPriority(e.target.value)} aria-label="Filter by priority"><option value="all">All priorities</option><option value="low">Low Priority</option><option value="medium">Medium Priority</option><option value="high">High Priority</option><option value="critical">Critical Priority</option></select><button type="button" className="clear-project-filters" onClick={clearFilters}>Clear</button></div></section>
        <div className="project-results-header project-studio-results-heading"><div><span className="workspace-eyebrow">Your workspaces</span><h2>Projects</h2><p>{filtered.length} visible</p></div></div>
        {filtered.length ? <section className="project-studio-grid">{filtered.map((card) => <ProjectCardView key={card.id} card={card} />)}</section> : <EmptyState title="No matching projects" text="Try a different search, status, or priority." />}
      </> : <article className="panel-card"><EmptyState title="Create your first project workspace" text="Connect goals, tasks, notes, documents, and progress in one place." /><div className="center-actions"><button className="primary-button" onClick={() => setCreateOpen(true)}>+ Create first project</button></div></article>}
    </section>
  );
}
