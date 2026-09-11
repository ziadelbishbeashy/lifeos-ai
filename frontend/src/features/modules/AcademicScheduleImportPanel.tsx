import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { AssessmentImportProposal, LearningModule } from "../../api/types";
import { ApiError } from "../../api/client";
import {
  confirmSelectedAssessmentImportProposals,
  dismissAssessmentImportProposal,
  importAcademicSchedule,
  moduleKeys,
  updateAssessmentImportProposal,
} from "./api";

const TYPES = ["Quiz", "Assignment", "Midterm", "Final", "Project", "Presentation", "Lab", "Other"];

function isAutoSelectable(proposal: AssessmentImportProposal) {
  return proposal.payload.module_id != null && proposal.payload.review_state === "ready";
}

export function AcademicScheduleImportPanel({ modules, onClose }: { modules: LearningModule[]; onClose: () => void }) {
  const qc = useQueryClient();
  const [proposals, setProposals] = useState<AssessmentImportProposal[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [sourceName, setSourceName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const moduleMap = useMemo(() => new Map(modules.map((module) => [module.id, module])), [modules]);

  const upload = useMutation({
    mutationFn: importAcademicSchedule,
    onSuccess: (data) => {
      setProposals(data.proposals);
      setSourceName(data.document.original_upload_name);
      // Trust-first default: only high-confidence, fully validated rows are preselected.
      // Needs-review rows stay visible and may still be explicitly selected by the user.
      setSelected(new Set(data.proposals.filter(isAutoSelectable).map((proposal) => proposal.id)));
      setError(null);
      setMessage(`V-SPACE found ${data.proposals.length} proposed assessment${data.proposals.length === 1 ? "" : "s"}. Review them before confirming.`);
    },
    onError: (value) => setError(value instanceof ApiError ? value.message : "V-SPACE could not read that academic schedule."),
  });

  const patch = useMutation({
    mutationFn: ({ id, input }: { id: number; input: Record<string, unknown> }) => updateAssessmentImportProposal(id, input),
    onSuccess: ({ proposal }) => {
      setProposals((rows) => rows.map((row) => row.id === proposal.id ? proposal : row));
      setSelected((old) => {
        if (proposal.payload.module_id != null && proposal.payload.review_state !== "possible_duplicate") return old;
        const next = new Set(old);
        next.delete(proposal.id);
        return next;
      });
      setError(null);
    },
    onError: (value) => setError(value instanceof ApiError ? value.message : "V-SPACE could not update that proposal."),
  });

  const dismiss = useMutation({
    mutationFn: dismissAssessmentImportProposal,
    onSuccess: ({ proposal }) => {
      setProposals((rows) => rows.filter((row) => row.id !== proposal.id));
      setSelected((old) => { const next = new Set(old); next.delete(proposal.id); return next; });
    },
    onError: (value) => setError(value instanceof ApiError ? value.message : "V-SPACE could not dismiss that proposal."),
  });

  const confirm = useMutation({
    mutationFn: confirmSelectedAssessmentImportProposals,
    onSuccess: async (data) => {
      const done = new Set(data.confirmed.map((proposal) => proposal.id));
      setProposals((rows) => rows.filter((proposal) => !done.has(proposal.id)));
      setSelected((old) => new Set([...old].filter((id) => !done.has(id))));
      setError(data.failed.length ? data.failed.map((failure) => failure.message).join(" ") : null);
      setMessage(data.confirmed.length ? `${data.confirmed.length} assessment${data.confirmed.length === 1 ? "" : "s"} added to the matched modules.` : null);
      await qc.invalidateQueries({ queryKey: moduleKeys.all });
    },
    onError: (value) => setError(value instanceof ApiError ? value.message : "V-SPACE could not confirm the selected assessments."),
  });

  function field(id: number, name: string, value: unknown) {
    patch.mutate({ id, input: { [name]: value === "" ? null : value } });
  }

  function draftField(id: number, name: string, value: unknown) {
    setProposals((rows) => rows.map((row) => row.id === id ? { ...row, payload: { ...row.payload, [name]: value } } : row));
  }

  return <section className="academic-import-panel">
    <div className="academic-import-head">
      <div>
        <span className="workspace-eyebrow">I21.2 Intelligent Academic Schedule</span>
        <h2>Import an exam timetable</h2>
        <p>Upload one photo, screenshot, or PDF. V-SPACE reads the schedule, matches rows to your existing modules, and creates nothing until you confirm.</p>
      </div>
      <button className="brain-text-button" type="button" onClick={onClose}>Close</button>
    </div>

    <label className="academic-dropzone">
      <input
        type="file"
        accept="application/pdf,.pdf,image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
        onChange={(event) => { const file = event.target.files?.[0]; if (file) upload.mutate(file); }}
      />
      <strong>{upload.isPending ? "Reading schedule…" : "Choose timetable photo / screenshot / PDF"}</strong>
      <span>OCR + existing Document Brain evidence · no direct AI writes</span>
    </label>

    {error ? <div className="brain-alert is-error">{error}</div> : null}
    {message ? <div className="brain-alert is-success">{message}</div> : null}
    {sourceName ? <div className="academic-import-source">Source: <strong>{sourceName}</strong></div> : null}

    <div className="academic-proposal-list">
      {proposals.map((proposal) => {
        const payload = proposal.payload;
        const module = payload.module_id ? moduleMap.get(payload.module_id) : null;
        const checked = selected.has(proposal.id);
        const selectable = payload.module_id != null && payload.review_state !== "possible_duplicate";
        return <article className={`academic-proposal-card state-${payload.review_state}`} key={proposal.id}>
          <div className="academic-proposal-top">
            <label className="academic-select" title={!selectable ? "Resolve this proposal before confirming it." : "Select for confirmation"}>
              <input
                type="checkbox"
                checked={checked}
                disabled={!selectable}
                onChange={(event) => setSelected((old) => {
                  const next = new Set(old);
                  event.target.checked ? next.add(proposal.id) : next.delete(proposal.id);
                  return next;
                })}
              />
            </label>
            <div>
              <span className="workspace-eyebrow">{payload.assessment_type} · {payload.review_state.replace(/_/g, " ")}</span>
              <h3>{payload.title}</h3>
              <p>{payload.source_module_text || "Module name not clear in source"} → <strong>{module?.title || "Choose module"}</strong></p>
            </div>
            <button className="brain-text-button is-danger" type="button" onClick={() => dismiss.mutate(proposal.id)}>Dismiss</button>
          </div>

          {payload.review_state === "needs_module" ? <div className="brain-alert is-warning">V-SPACE could not safely decide which module this belongs to. Choose the correct module before confirming.</div> : null}
          {payload.review_state === "needs_review" ? <div className="brain-alert is-warning">Some information is uncertain or missing. Check the source evidence and edit anything needed before selecting this row.</div> : null}
          {payload.review_state === "possible_duplicate" ? <div className="brain-alert is-warning">Possible duplicate of assessment #{payload.duplicate_assessment_id}. V-SPACE will not create it unless the proposal is changed so it is no longer a duplicate.</div> : null}

          <div className="academic-edit-grid">
            <label><span>Module</span><select value={payload.module_id ?? ""} onChange={(event) => field(proposal.id, "module_id", event.target.value)}><option value="">Needs review</option>{modules.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
            <label><span>Type</span><select value={payload.assessment_type} onChange={(event) => field(proposal.id, "assessment_type", event.target.value)}>{TYPES.map((type) => <option key={type}>{type}</option>)}</select></label>
            <label className="wide"><span>Title</span><input value={payload.title} onChange={(event) => draftField(proposal.id, "title", event.target.value)} onBlur={(event) => field(proposal.id, "title", event.target.value)} /></label>
            <label><span>Exam date</span><input type="date" value={payload.assessment_date || ""} onChange={(event) => field(proposal.id, "assessment_date", event.target.value)} /></label>
            <label><span>Exam time</span><input type="time" value={payload.assessment_time || ""} onChange={(event) => field(proposal.id, "assessment_time", event.target.value)} /></label>
            <label><span>Due date</span><input type="date" value={payload.due_date || ""} onChange={(event) => field(proposal.id, "due_date", event.target.value)} /></label>
            <label><span>Due time</span><input type="time" value={payload.due_time || ""} onChange={(event) => field(proposal.id, "due_time", event.target.value)} /></label>
            <label><span>Weight %</span><input type="number" min="0" max="100" step="0.01" value={payload.weight_percent ?? ""} onChange={(event) => draftField(proposal.id, "weight_percent", event.target.value)} onBlur={(event) => field(proposal.id, "weight_percent", event.target.value)} /></label>
            <label><span>Prep minutes</span><input type="number" min="0" value={payload.estimated_study_minutes ?? ""} onChange={(event) => draftField(proposal.id, "estimated_study_minutes", event.target.value)} onBlur={(event) => field(proposal.id, "estimated_study_minutes", event.target.value)} /></label>
            <label className="wide"><span>Topics</span><input value={payload.topics || ""} onChange={(event) => draftField(proposal.id, "topics", event.target.value)} onBlur={(event) => field(proposal.id, "topics", event.target.value)} placeholder="Only if stated, or add your own after review" /></label>
            <label className="wide"><span>Notes</span><textarea rows={2} value={payload.notes || ""} onChange={(event) => draftField(proposal.id, "notes", event.target.value)} onBlur={(event) => field(proposal.id, "notes", event.target.value)} /></label>
          </div>

          <details className="academic-evidence">
            <summary>Source evidence · {payload.extraction_confidence} extraction confidence</summary>
            {proposal.evidence.map((evidence, index) => <div key={`${proposal.id}-e-${index}`}>
              <strong>{evidence.original_upload_name || evidence.source_filename}{evidence.page ? ` · Page ${evidence.page}` : ""}</strong>
              <blockquote>{evidence.excerpt || "Evidence retained by V-SPACE."}</blockquote>
              {evidence.document_id ? <a href={`/documents/${evidence.document_id}?tab=pdf${evidence.page ? `&page=${String(evidence.page).split("-")[0]}` : ""}`} className="workspace-secondary-button compact">Open source</a> : null}
            </div>)}
          </details>
        </article>;
      })}
    </div>

    {proposals.length ? <div className="academic-confirm-bar">
      <span>{selected.size} selected</span>
      <button className="workspace-primary-button" type="button" disabled={!selected.size || confirm.isPending || patch.isPending} onClick={() => confirm.mutate([...selected])}>{confirm.isPending ? "Confirming…" : `Confirm ${selected.size} selected`}</button>
    </div> : null}
  </section>;
}
