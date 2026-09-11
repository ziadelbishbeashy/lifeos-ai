import { useMemo, useState, type FormEvent } from "react";
import type { ProjectSummary, Task, TaskInput } from "../../api/types";

const statuses = ["Pending", "In Progress", "Blocked", "Completed"];
const importance = ["Low", "Medium", "High", "Critical"];
const difficulty = ["Easy", "Medium", "Hard"];
const reminderTypes = [
  ["custom", "Custom date/time"],
  ["due_time", "On due date"],
  ["one_day_before", "One day before"],
  ["three_days_before", "Three days before"],
  ["one_hour_before", "One hour before"],
] as const;
const recurrenceTypes = [
  ["daily", "Daily"],
  ["weekly", "Weekly"],
  ["monthly", "Monthly"],
  ["custom_days", "Every N days"],
] as const;

type Props = {
  projects: ProjectSummary[];
  initial?: Task | null;
  forcedProjectId?: number;
  submitLabel: string;
  busy?: boolean;
  onSubmit: (input: TaskInput) => void | Promise<void>;
  onCancel?: () => void;
};

function reminderParts(value: string | null | undefined) {
  if (!value) return { date: "", time: "09:00" };
  const [date, rawTime] = value.split("T");
  return { date: date ?? "", time: rawTime?.slice(0, 5) || "09:00" };
}

export function TaskForm({ projects, initial, forcedProjectId, submitLabel, busy, onSubmit, onCancel }: Props) {
  const defaults = useMemo<TaskInput>(() => {
    const reminder = reminderParts(initial?.reminder_datetime);
    return {
      title: initial?.title ?? "",
      description: initial?.description ?? "",
      project_id: forcedProjectId ?? initial?.project_id ?? null,
      module: initial?.module ?? "",
      tags: initial?.tags ?? "",
      importance: initial?.importance ?? "Medium",
      difficulty: initial?.difficulty ?? "Medium",
      deadline: initial?.deadline ?? "",
      status: initial?.status ?? "Pending",
      forced_project_id: forcedProjectId,
      reminder_enabled: initial?.reminder_enabled ?? false,
      reminder_type: initial?.reminder_type && initial.reminder_type !== "none" ? initial.reminder_type : "custom",
      reminder_date: reminder.date,
      reminder_time: reminder.time,
      is_recurring: initial?.is_recurring ?? false,
      recurrence_type: initial?.recurrence_type && initial.recurrence_type !== "none" ? initial.recurrence_type : "daily",
      recurrence_interval: initial?.recurrence_interval ?? 1,
      recurrence_end_date: initial?.recurrence_end_date ?? "",
    };
  }, [initial, forcedProjectId]);

  const [form, setForm] = useState<TaskInput>(defaults);

  function update<K extends keyof TaskInput>(key: K, value: TaskInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    await onSubmit(form);
  }

  return (
    <form className="workspace-form" onSubmit={submit}>
      <label>
        <span>Task title</span>
        <input required maxLength={200} value={form.title} onChange={(e) => update("title", e.target.value)} />
      </label>

      <label>
        <span>Description</span>
        <textarea rows={3} value={form.description ?? ""} onChange={(e) => update("description", e.target.value)} />
      </label>

      {!forcedProjectId ? (
        <label>
          <span>Project</span>
          <select
            value={form.project_id ?? ""}
            onChange={(e) => update("project_id", e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">General workspace</option>
            {projects.map((project) => <option key={project.id} value={project.id}>{project.title}</option>)}
          </select>
        </label>
      ) : null}

      <div className="form-grid three">
        <label>
          <span>Status</span>
          <select value={form.status} onChange={(e) => update("status", e.target.value)}>
            {statuses.map((status) => <option key={status}>{status}</option>)}
          </select>
        </label>
        <label>
          <span>Importance</span>
          <select value={form.importance} onChange={(e) => update("importance", e.target.value)}>
            {importance.map((level) => <option key={level}>{level}</option>)}
          </select>
        </label>
        <label>
          <span>Difficulty</span>
          <select value={form.difficulty} onChange={(e) => update("difficulty", e.target.value)}>
            {difficulty.map((level) => <option key={level}>{level}</option>)}
          </select>
        </label>
      </div>

      <div className="form-grid three">
        <label>
          <span>Deadline</span>
          <input type="date" value={form.deadline ?? ""} onChange={(e) => update("deadline", e.target.value)} />
        </label>
        <label>
          <span>Module / area</span>
          <input value={form.module ?? ""} onChange={(e) => update("module", e.target.value)} />
        </label>
        <label>
          <span>Tags</span>
          <input value={form.tags ?? ""} placeholder="backend, api" onChange={(e) => update("tags", e.target.value)} />
        </label>
      </div>

      <div className="advanced-task-grid">
        <fieldset className="advanced-task-box">
          <legend>Reminder</legend>
          <label className="inline-check">
            <input type="checkbox" checked={Boolean(form.reminder_enabled)} onChange={(e) => update("reminder_enabled", e.target.checked)} />
            <span>Enable reminder</span>
          </label>
          {form.reminder_enabled ? (
            <div className="form-grid three">
              <label>
                <span>Reminder rule</span>
                <select value={form.reminder_type} onChange={(e) => update("reminder_type", e.target.value)}>
                  {reminderTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
              {form.reminder_type === "custom" ? (
                <label>
                  <span>Reminder date</span>
                  <input required type="date" value={form.reminder_date ?? ""} onChange={(e) => update("reminder_date", e.target.value)} />
                </label>
              ) : <div />}
              <label>
                <span>Reminder time</span>
                <input required type="time" value={form.reminder_time ?? "09:00"} onChange={(e) => update("reminder_time", e.target.value)} />
              </label>
            </div>
          ) : null}
        </fieldset>

        <fieldset className="advanced-task-box">
          <legend>Recurrence</legend>
          <label className="inline-check">
            <input type="checkbox" checked={Boolean(form.is_recurring)} onChange={(e) => update("is_recurring", e.target.checked)} />
            <span>Repeat this task</span>
          </label>
          {form.is_recurring ? (
            <div className="form-grid three">
              <label>
                <span>Pattern</span>
                <select value={form.recurrence_type} onChange={(e) => update("recurrence_type", e.target.value)}>
                  {recurrenceTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
              <label>
                <span>Interval</span>
                <input type="number" min={1} max={365} value={form.recurrence_interval ?? 1} onChange={(e) => update("recurrence_interval", Number(e.target.value))} />
              </label>
              <label>
                <span>Repeat until</span>
                <input type="date" value={form.recurrence_end_date ?? ""} onChange={(e) => update("recurrence_end_date", e.target.value)} />
              </label>
            </div>
          ) : null}
        </fieldset>
      </div>

      <div className="form-actions">
        <button className="primary-button" disabled={busy} type="submit">{busy ? "Saving…" : submitLabel}</button>
        {onCancel ? <button className="secondary-button" type="button" onClick={onCancel}>Cancel</button> : null}
      </div>
    </form>
  );
}
