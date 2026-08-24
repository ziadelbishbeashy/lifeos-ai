import { useMemo, useState, type FormEvent } from "react";
import type { Project, ProjectInput } from "../../api/types";

const statuses = ["Planning", "In Progress", "Paused", "Completed"];
const priorities = ["Low", "Medium", "High", "Critical"];

type Props = {
  initial?: Project | null;
  submitLabel: string;
  busy?: boolean;
  onSubmit: (input: ProjectInput) => void | Promise<void>;
  onCancel?: () => void;
};

export function ProjectForm({ initial, submitLabel, busy, onSubmit, onCancel }: Props) {
  const defaults = useMemo<ProjectInput>(() => ({
    title: initial?.title ?? "",
    project_type: initial?.project_type ?? "",
    description: initial?.description ?? "",
    goal: initial?.goal ?? "",
    tech_stack: initial?.tech_stack ?? "",
    project_folder: initial?.project_folder ?? "",
    github_link: initial?.github_link ?? "",
    demo_link: initial?.demo_link ?? "",
    start_date: initial?.start_date ?? "",
    deadline: initial?.deadline ?? "",
    no_deadline: initial ? initial.deadline === null : false,
    status: initial?.status ?? "In Progress",
    priority: initial?.priority ?? "Medium",
    current_phase: initial?.current_phase ?? "",
    progress: initial?.progress ?? 0,
  }), [initial]);

  const [form, setForm] = useState<ProjectInput>(defaults);

  function update<K extends keyof ProjectInput>(key: K, value: ProjectInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    await onSubmit({
      ...form,
      deadline: form.no_deadline ? "" : form.deadline,
    });
  }

  return (
    <form className="workspace-form" onSubmit={submit}>
      <div className="form-grid two">
        <label>
          <span>Project title</span>
          <input required maxLength={150} value={form.title} onChange={(e) => update("title", e.target.value)} />
        </label>
        <label>
          <span>Project type</span>
          <input value={form.project_type ?? ""} placeholder="AI, software, research…" onChange={(e) => update("project_type", e.target.value)} />
        </label>
      </div>

      <label>
        <span>Goal</span>
        <textarea rows={2} value={form.goal ?? ""} onChange={(e) => update("goal", e.target.value)} />
      </label>
      <label>
        <span>Description</span>
        <textarea rows={3} value={form.description ?? ""} onChange={(e) => update("description", e.target.value)} />
      </label>

      <div className="form-grid three">
        <label>
          <span>Status</span>
          <select value={form.status} onChange={(e) => update("status", e.target.value)}>
            {statuses.map((status) => <option key={status}>{status}</option>)}
          </select>
        </label>
        <label>
          <span>Priority</span>
          <select value={form.priority} onChange={(e) => update("priority", e.target.value)}>
            {priorities.map((priority) => <option key={priority}>{priority}</option>)}
          </select>
        </label>
        <label>
          <span>Progress</span>
          <input type="number" min={0} max={100} value={form.progress ?? 0} onChange={(e) => update("progress", Number(e.target.value))} />
        </label>
      </div>

      <div className="form-grid three">
        <label>
          <span>Current phase</span>
          <input value={form.current_phase ?? ""} onChange={(e) => update("current_phase", e.target.value)} />
        </label>
        <label>
          <span>Start date</span>
          <input type="date" value={form.start_date ?? ""} onChange={(e) => update("start_date", e.target.value)} />
        </label>
        <label>
          <span>Deadline</span>
          <input type="date" disabled={Boolean(form.no_deadline)} value={form.deadline ?? ""} onChange={(e) => update("deadline", e.target.value)} />
        </label>
      </div>

      <label className="inline-check">
        <input type="checkbox" checked={Boolean(form.no_deadline)} onChange={(e) => update("no_deadline", e.target.checked)} />
        <span>No deadline</span>
      </label>

      <label>
        <span>Tech stack</span>
        <input value={form.tech_stack ?? ""} placeholder="React, Flask, PostgreSQL…" onChange={(e) => update("tech_stack", e.target.value)} />
      </label>

      <div className="form-grid three">
        <label>
          <span>Project folder</span>
          <input value={form.project_folder ?? ""} onChange={(e) => update("project_folder", e.target.value)} />
        </label>
        <label>
          <span>GitHub link</span>
          <input type="url" value={form.github_link ?? ""} onChange={(e) => update("github_link", e.target.value)} />
        </label>
        <label>
          <span>Demo link</span>
          <input type="url" value={form.demo_link ?? ""} onChange={(e) => update("demo_link", e.target.value)} />
        </label>
      </div>

      <div className="form-actions">
        <button className="primary-button" disabled={busy} type="submit">{busy ? "Saving…" : submitLabel}</button>
        {onCancel ? <button className="secondary-button" type="button" onClick={onCancel}>Cancel</button> : null}
      </div>
    </form>
  );
}
