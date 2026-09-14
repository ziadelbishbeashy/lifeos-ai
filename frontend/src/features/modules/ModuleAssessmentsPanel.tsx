import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import type { ModuleAssessment } from "../../api/types";
import { ApiError } from "../../api/client";
import { createModuleAssessment, deleteModuleAssessment, updateModuleAssessment } from "./api";
import { formatTime12h, TimePicker12hField } from "../../components/TimePicker12h";

const TYPES = ["Quiz", "Assignment", "Midterm", "Final", "Project", "Presentation", "Lab", "Other"];

function formPayload(form: FormData) {
  return {
    title: String(form.get("title") || "").trim(), assessment_type: String(form.get("assessment_type") || "Other"),
    assessment_date: String(form.get("assessment_date") || "") || null, assessment_time: String(form.get("assessment_time") || "") || null,
    due_date: String(form.get("due_date") || "") || null, due_time: String(form.get("due_time") || "") || null,
    weight_percent: String(form.get("weight_percent") || "") || null, status: String(form.get("status") || "Upcoming"),
    topics: String(form.get("topics") || "").trim() || null, estimated_study_minutes: String(form.get("estimated_study_minutes") || "") || null,
    notes: String(form.get("notes") || "").trim() || null,
  };
}

function AssessmentFields({ value, editing = false }: { value?: ModuleAssessment; editing?: boolean }) {
  return <>
    <label><span>Assessment</span><input name="title" required defaultValue={value?.title || ""} placeholder="e.g. Calculus midterm" /></label>
    <label><span>Type</span><select name="assessment_type" defaultValue={value?.assessment_type || "Quiz"}>{TYPES.map(t => <option key={t}>{t}</option>)}</select></label>
    <label><span>Exam / event date</span><input name="assessment_date" type="date" defaultValue={value?.assessment_date || ""} /></label>
    <label><span>Start time</span><TimePicker12hField name="assessment_time" defaultValue={value?.assessment_time?.slice(0,5) || ""} allowEmpty ariaLabel="Assessment time" /></label>
    <label><span>Due date</span><input name="due_date" type="date" defaultValue={value?.due_date || ""} /></label>
    <label><span>Due time</span><TimePicker12hField name="due_time" defaultValue={value?.due_time?.slice(0,5) || ""} allowEmpty ariaLabel="Due time" /></label>
    <label><span>Weight %</span><input name="weight_percent" type="number" min="0" max="100" step="0.01" defaultValue={value?.weight_percent ?? ""} placeholder="30" /></label>
    <label><span>Preparation time</span><input name="estimated_study_minutes" type="number" min="0" step="15" defaultValue={value?.estimated_study_minutes ?? ""} placeholder="e.g. 300 minutes" /></label>
    {editing ? <label><span>Status</span><select name="status" defaultValue={value?.status || "Upcoming"}><option>Upcoming</option><option>In Progress</option><option>Completed</option><option>Cancelled</option></select></label> : null}
    <label className="wide"><span>Topics to prepare</span><input name="topics" defaultValue={value?.topics || ""} placeholder="Integration, series, practice questions" /></label>
    <label className="wide"><span>Notes</span><textarea name="notes" rows={2} defaultValue={value?.notes || ""} placeholder="Anything V-SPACE should know about this assessment" /></label>
  </>;
}

export function ModuleAssessmentsPanel({ moduleId, assessments, refresh }: { moduleId: number; assessments: ModuleAssessment[]; refresh: () => Promise<void> }) {
  const [showForm, setShowForm] = useState(false); const [editingId, setEditingId] = useState<number | null>(null); const [error, setError] = useState<string | null>(null);
  const fail = (v: unknown) => setError(v instanceof ApiError ? v.message : "V-SPACE could not update the assessment.");
  const create = useMutation({ mutationFn: (input: Record<string, unknown>) => createModuleAssessment(moduleId, input), onSuccess: async () => { setError(null); setShowForm(false); await refresh(); }, onError: fail });
  const update = useMutation({ mutationFn: ({ id, input }: { id: number; input: Record<string, unknown> }) => updateModuleAssessment(moduleId, id, input), onSuccess: async () => { setError(null); setEditingId(null); await refresh(); }, onError: fail });
  const remove = useMutation({ mutationFn: (id: number) => deleteModuleAssessment(moduleId, id), onSuccess: async () => { setError(null); await refresh(); }, onError: fail });
  function submitCreate(e: FormEvent<HTMLFormElement>) { e.preventDefault(); create.mutate(formPayload(new FormData(e.currentTarget))); }
  function submitEdit(e: FormEvent<HTMLFormElement>, id: number) { e.preventDefault(); update.mutate({ id, input: formPayload(new FormData(e.currentTarget)) }); }
  return <article className="module-panel module-assessment-panel">
    <div className="module-section-heading"><div><span className="workspace-eyebrow">Academic schedule</span><h2>Assessments</h2><p>Add the real date, time, topics and preparation effort. V-SPACE can then protect the assessment time and use the preparation estimate when planning.</p></div><button className="workspace-secondary-button" type="button" onClick={() => setShowForm(v => !v)}>{showForm ? "Close" : "+ Manual"}</button></div>
    {error ? <div className="brain-alert is-error">{error}</div> : null}
    {showForm ? <form className="assessment-manual-form" onSubmit={submitCreate}><AssessmentFields /><button className="workspace-primary-button" disabled={create.isPending}>{create.isPending ? "Saving…" : "Add assessment"}</button></form> : null}
    <div className="assessment-list">{assessments.map(a => <div key={a.id}>
      <article className="assessment-row"><div className="assessment-date-badge"><strong>{a.target_date ? new Date(`${a.target_date}T00:00:00`).toLocaleDateString(undefined,{month:"short",day:"numeric"}) : "—"}</strong><span>{formatTime12h(a.target_time?.slice(0,5) || "")}</span></div><div className="assessment-row-main"><span className="workspace-eyebrow">{a.assessment_type}{a.weight_percent != null ? ` · ${a.weight_percent}%` : ""}</span><strong>{a.title}</strong><small>{a.timing_label || "Date not set"}{a.topics ? ` · ${a.topics}` : ""}</small><small>{a.estimated_study_minutes ? `${a.estimated_study_minutes} min preparation · ${a.planner_ready ? "ready for Smart Planner" : "not scheduled"}` : "Add preparation time to let Smart Planner prepare for this assessment."}</small></div><div className="assessment-row-actions"><button className="brain-text-button" type="button" onClick={() => setEditingId(editingId === a.id ? null : a.id)}>{editingId === a.id ? "Close edit" : "Edit"}</button>{a.status !== "Completed" ? <button className="brain-text-button" type="button" onClick={() => update.mutate({id:a.id,input:{status:"Completed"}})}>Complete</button> : <button className="brain-text-button" type="button" onClick={() => update.mutate({id:a.id,input:{status:"Upcoming"}})}>Reopen</button>}<button className="brain-text-button is-danger" type="button" onClick={() => { if(window.confirm(`Delete “${a.title}”?`)) remove.mutate(a.id); }}>Delete</button></div></article>
      {editingId === a.id ? <form className="assessment-manual-form assessment-edit-form" onSubmit={(e) => submitEdit(e, a.id)}><AssessmentFields value={a} editing /><button className="workspace-primary-button" disabled={update.isPending}>{update.isPending ? "Saving…" : "Save changes"}</button></form> : null}
    </div>)}{!assessments.length ? <div className="module-inline-empty">No assessments yet. Import an exam schedule from Modules, or add one manually.</div> : null}</div>
  </article>;
}
