import { useMutation, useQuery } from "@tanstack/react-query";
import type { FormEvent } from "react";
import { ApiError } from "../api/client";
import type { ProjectCard, ProjectInput } from "../api/types";
import { useSession } from "../auth/session";
import { createProject, fetchProjects, projectKeys } from "../features/projects/api";
import { NativeWorkspaceShell } from "../native/NativeWorkspaceShell";
import { useNativeLegacyAssets } from "../native/useNativeLegacyAssets";

const projectTypes = [
  "Full-Stack AI System",
  "Web Application",
  "Mobile Application",
  "Machine Learning Project",
  "Graduation Project",
  "Portfolio Project",
  "Research Project",
  "Job Preparation",
  "Other",
];

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
  const limit = Math.max(0, max - 3);
  const candidate = value.slice(0, limit);
  const boundary = candidate.lastIndexOf(" ");
  const shortened = (boundary > Math.floor(limit * 0.6) ? candidate.slice(0, boundary) : candidate).trimEnd();
  return `${shortened}...`;
}

function slug(value: string) {
  return value.toLowerCase().replace(/\s+/g, "-");
}

function projectInputFromForm(form: HTMLFormElement): ProjectInput {
  const data = new FormData(form);
  const read = (name: string) => String(data.get(name) ?? "").trim();
  const noDeadline = data.get("no_deadline") !== null;
  const rawProgress = Number(read("progress") || 0);

  return {
    title: read("title"),
    project_type: read("project_type"),
    description: read("description"),
    goal: read("goal"),
    tech_stack: read("tech_stack"),
    project_folder: read("project_folder"),
    github_link: read("github_link"),
    demo_link: read("demo_link"),
    start_date: read("start_date"),
    deadline: noDeadline ? "" : read("deadline"),
    no_deadline: noDeadline,
    status: read("status") || "In Progress",
    priority: read("priority") || "Medium",
    current_phase: read("current_phase"),
    progress: Number.isFinite(rawProgress) ? rawProgress : 0,
  };
}

function ProjectCardView({ card }: { card: ProjectCard }) {
  const summary = card.goal || card.description || "No project goal has been added yet.";
  const type = card.project_type || "Project";
  const healthTone = card.health?.tone || "neutral";
  const healthLabel = card.health?.label || "On track";
  const healthMessage = card.health?.message || "No urgent project signal detected.";
  const status = card.status || "In Progress";
  const priority = card.priority || "Medium";

  return (
    <article
      className="project-studio-card"
      data-project-card
      data-title={card.title.toLowerCase()}
      data-description={(card.description || card.goal || "").toLowerCase()}
      data-type={(card.project_type || "").toLowerCase()}
      data-stack={(card.tech_stack || "").toLowerCase()}
      data-phase={(card.current_phase || "").toLowerCase()}
      data-status={status.toLowerCase()}
      data-priority={priority.toLowerCase()}
    >
      <div className="project-studio-card-topline">
        <div className="project-studio-card-identity">
          <span className="project-studio-avatar">{card.title.charAt(0).toUpperCase()}</span>
          <div>
            <span className="workspace-eyebrow">{type}</span>
            <h3>{card.title}</h3>
          </div>
        </div>
        <span className={`project-health-pill project-health-${healthTone}`}>{healthLabel}</span>
      </div>

      <p className="project-studio-card-summary">{truncate(summary)}</p>

      <div className="project-studio-progress-row">
        <div><span>Execution progress</span><strong>{card.task_progress}%</strong></div>
        <div className="professional-progress-track">
          <div className="professional-progress-fill" data-progress={card.task_progress} />
        </div>
      </div>

      <div className="project-studio-signal-row">
        <span><strong>{card.open_tasks}</strong> open tasks</span>
        <span><strong>{card.note_count}</strong> notes</span>
        {card.deadline ? <span>Due {formatDate(card.deadline)}</span> : <span>No project deadline</span>}
      </div>

      <div className="project-studio-health-copy">
        <span>Current signal</span>
        <p>{healthMessage}</p>
      </div>

      <div className="project-studio-next-action">
        <span>Next action</span>
        {card.next_task ? (
          <>
            <strong>{card.next_task.title}</strong>
            <small>
              {card.next_task.status} · {card.next_task.importance || "Medium"} priority
              {card.next_task.deadline ? ` · Due ${formatDate(card.next_task.deadline, false)}` : ""}
            </small>
          </>
        ) : (
          <>
            <strong>{status === "Completed" ? "Project complete" : "Add the first actionable task"}</strong>
            <small>{status === "Completed" ? "No unfinished tasks remain." : "Turn the project goal into a clear next step."}</small>
          </>
        )}
      </div>

      <div className="project-studio-card-footer">
        <div className="project-studio-badges">
          <span className={`project-status-badge project-status-${slug(status)}`}>{status}</span>
          <span className={`project-priority-badge project-priority-${priority.toLowerCase()}`}>{priority}</span>
        </div>
        <a href={`/projects/${card.id}`} className="workspace-primary-button project-studio-open-button" data-page-loading data-loading-title="Opening project" data-loading-message="Loading the project workspace...">Open Project</a>
      </div>
    </article>
  );
}

export function ProjectsPage() {
  const session = useSession();
  const projects = useQuery({
    queryKey: projectKeys.all,
    queryFn: fetchProjects,
    retry: false,
    enabled: session.data?.authenticated === true,
  });
  const createMutation = useMutation({ mutationFn: createProject });

  const ready = Boolean(session.data?.authenticated && session.data.user && projects.data);
  useNativeLegacyAssets(ready, session.data?.user?.id);

  if (session.data && !session.data.authenticated) {
    window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
    return null;
  }

  if (session.isPending || projects.isPending) {
    return <main className="react-parity-state"><div className="react-parity-card"><strong>Opening projects</strong><p>Loading your project workspace...</p></div></main>;
  }

  if (session.isError || projects.isError || !session.data?.user || !projects.data) {
    return <main className="react-parity-state"><div className="react-parity-card"><strong>Projects could not open</strong><p>LifeOS could not load the Projects API.</p><button type="button" onClick={() => window.location.reload()}>Retry</button></div></main>;
  }

  const data = projects.data;
  const user = session.data.user;
  const createError = createMutation.error instanceof ApiError ? createMutation.error.message : createMutation.isError ? "The project could not be created." : null;

  async function submitProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const input = projectInputFromForm(form);

    try {
      (window as any).lifeOSLoading?.button?.((event.nativeEvent as SubmitEvent).submitter);
      (window as any).lifeOSLoading?.show?.({
        title: "Creating project",
        message: "LifeOS is setting up your new workspace project...",
      });
      await createMutation.mutateAsync(input);
      window.location.replace("/projects");
    } catch (error) {
      console.error(error);
      (window as any).lifeOSLoading?.hide?.();
      const submitButton = form.querySelector<HTMLButtonElement>('button[type="submit"]');
      if (submitButton) {
        submitButton.classList.remove("is-loading");
        submitButton.disabled = false;
        submitButton.removeAttribute("aria-busy");
      }
      const overlay = document.getElementById("projectModalOverlay");
      overlay?.classList.add("open");
      overlay?.setAttribute("aria-hidden", "false");
      document.body.classList.add("project-modal-open");
    }
  }

  return (
    <NativeWorkspaceShell user={user} active="projects">
      <div className="projects-page project-studio-index">
        <header className="workspace-page-header project-studio-index-header">
          <div>
            <span className="workspace-eyebrow">Project workspace</span>
            <h1>Keep every project moving.</h1>
            <p>See what needs attention, continue the right task, and keep notes and execution connected without opening every project.</p>
          </div>
          <button type="button" className="workspace-primary-button" data-open-project-modal>+ New Project</button>
        </header>

        <section className="project-studio-summary" aria-label="Project summary">
          <article><span>Active projects</span><strong>{data.counts.active}</strong><small>Currently moving</small></article>
          <article><span>Need attention</span><strong>{data.counts.attention}</strong><small>Overdue, blocked, or close to deadline</small></article>
          <article><span>Completed</span><strong>{data.counts.completed}</strong><small>Finished workspaces</small></article>
        </section>

        {data.items.length ? (
          <>
            <section className="project-filter-panel project-studio-filter">
              <div className="project-search-wrapper"><span className="project-search-icon">⌕</span><input type="search" id="projectSearchInput" placeholder="Search projects, goals, technologies, or phases..." autoComplete="off" /></div>
              <div className="project-filter-controls">
                <select id="projectStatusFilter" aria-label="Filter by status"><option value="all">All statuses</option><option value="planning">Planning</option><option value="in progress">In Progress</option><option value="paused">Paused</option><option value="completed">Completed</option></select>
                <select id="projectPriorityFilter" aria-label="Filter by priority"><option value="all">All priorities</option><option value="low">Low Priority</option><option value="medium">Medium Priority</option><option value="high">High Priority</option><option value="critical">Critical Priority</option></select>
                <button type="button" className="clear-project-filters" id="clearProjectFilters">Clear</button>
              </div>
            </section>

            <div className="project-results-header project-studio-results-heading"><div><span className="workspace-eyebrow">Your workspaces</span><h2>Projects</h2><p><span id="visibleProjectCount">{data.items.length}</span> visible</p></div></div>
            <section className="project-studio-grid" id="projectsGrid">{data.items.map((card) => <ProjectCardView key={card.id} card={card} />)}</section>
            <section className="task-no-results project-studio-no-results" id="projectNoResults" hidden><div>⌕</div><h3>No matching projects</h3><p>Try a different search, status, or priority.</p><button type="button" className="workspace-secondary-button" id="clearProjectFiltersEmpty">Clear Filters</button></section>
          </>
        ) : (
          <section className="professional-task-empty-state project-studio-empty-state"><div className="empty-task-symbol">P</div><span>Start with one meaningful goal</span><h2>Create your first project workspace</h2><p>Connect goals, tasks, notes, and progress in one place.</p><button type="button" className="workspace-primary-button" data-open-project-modal>+ Create First Project</button></section>
        )}
      </div>

      <div className="project-modal-overlay" id="projectModalOverlay" aria-hidden="true">
        <section className="project-modal" role="dialog" aria-modal="true" aria-labelledby="createProjectTitle">
          <div className="project-modal-header"><div><span className="workspace-eyebrow">New Workspace</span><h2 id="createProjectTitle">Create Project</h2><p>Add the main information for your new project.</p></div><button type="button" className="project-modal-close" data-close-project-modal aria-label="Close project form">×</button></div>
          {createError ? <div className="flash-container" aria-live="polite"><div className="flash flash-error"><span>{createError}</span></div></div> : null}
          <form method="POST" action="/api/v1/projects" className="professional-project-form" data-loading-title="Creating project" data-loading-message="LifeOS is setting up your new workspace project..." onSubmit={submitProject}>
            <div className="project-form-grid">
              <div className="project-form-field"><label htmlFor="projectTitle">Project title <span>*</span></label><input type="text" id="projectTitle" name="title" placeholder="Example: LifeOS AI" required /></div>
              <div className="project-form-field"><label htmlFor="projectType">Project type</label><select id="projectType" name="project_type"><option value="">Select project type</option>{projectTypes.map((type) => <option value={type} key={type}>{type}</option>)}</select></div>
              <div className="project-form-field project-form-full"><label htmlFor="projectDescription">Description</label><textarea id="projectDescription" name="description" placeholder="Describe the project and its main purpose..." /></div>
              <div className="project-form-field project-form-full"><label htmlFor="projectGoal">Main goal</label><textarea id="projectGoal" name="goal" placeholder="What should this project achieve?" /></div>
              <div className="project-form-field project-form-full"><label htmlFor="projectStack">Technology stack</label><input type="text" id="projectStack" name="tech_stack" placeholder="Flask, SQL Server, HTML, CSS, JavaScript" /></div>
              <div className="project-form-field"><label htmlFor="projectStatus">Status</label><select id="projectStatus" name="status" defaultValue="In Progress"><option value="Planning">Planning</option><option value="In Progress">In Progress</option><option value="Paused">Paused</option><option value="Completed">Completed</option></select></div>
              <div className="project-form-field"><label htmlFor="projectPriority">Priority</label><select id="projectPriority" name="priority" defaultValue="Medium"><option value="Low">Low</option><option value="Medium">Medium</option><option value="High">High</option><option value="Critical">Critical</option></select></div>
              <div className="project-form-field"><label htmlFor="projectStartDate">Start date</label><input type="date" id="projectStartDate" name="start_date" /></div>
              <div className="project-form-field"><label htmlFor="newProjectDeadline">Deadline</label><input type="date" id="newProjectDeadline" name="deadline" /><label className="professional-checkbox"><input type="checkbox" name="no_deadline" data-no-deadline data-deadline-target="newProjectDeadline" /><span>No deadline</span></label></div>
              <div className="project-form-field"><label htmlFor="projectPhase">Current phase</label><input type="text" id="projectPhase" name="current_phase" placeholder="Example: Backend development" /></div>
              <div className="project-form-field"><label htmlFor="projectProgress">Progress</label><div className="progress-input-wrapper"><input type="number" id="projectProgress" name="progress" min="0" max="100" defaultValue="0" /><span>%</span></div></div>
              <div className="project-form-divider project-form-full"><span>External Resources</span></div>
              <div className="project-form-field project-form-full"><label htmlFor="projectFolder">Local project folder</label><input type="text" id="projectFolder" name="project_folder" placeholder="C:\\Users\\Name\\Desktop\\project" /></div>
              <div className="project-form-field"><label htmlFor="projectGithub">GitHub repository</label><input type="url" id="projectGithub" name="github_link" placeholder="https://github.com/username/project" /></div>
              <div className="project-form-field"><label htmlFor="projectDemo">Live demo</label><input type="url" id="projectDemo" name="demo_link" placeholder="https://project-demo.com" /></div>
            </div>
            <div className="project-modal-actions"><button type="button" className="workspace-secondary-button" data-close-project-modal>Cancel</button><button type="submit" className="workspace-primary-button" disabled={createMutation.isPending}>{createMutation.isPending ? "Creating..." : "Create Project"}</button></div>
          </form>
        </section>
      </div>
    </NativeWorkspaceShell>
  );
}
