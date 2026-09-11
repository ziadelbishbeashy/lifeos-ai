import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ApiError, apiDelete, apiGet, apiPatch, apiPost } from "../api/client";
import { PageState } from "../components/NativeUi";


type PlannerProject = { id: number; title: string };
type PlannerCommitment = {
  id: number | string;
  title: string;
  date: string;
  start_time: string;
  end_time: string;
  commitment_type: string;
  notes: string | null;
  source: "manual" | "academic";
  editable: boolean;
  module_title?: string | null;
};
type PlannerBlock = {
  id?: number;
  task_id: number | null;
  title: string;
  date: string;
  start_time: string;
  end_time: string;
  minutes: number;
  block_type: string;
  project_id: number | null;
  project_title: string | null;
  importance: string | null;
  difficulty?: string | null;
  deadline: string | null;
  rationale: string | null;
  locked: boolean;
  preserved?: boolean;
  sort_order: number;
  task_status?: string | null;
  state?: "completed" | "missed" | "current" | "upcoming";
};
type PlannerDay = {
  date: string;
  label: string;
  blocks: PlannerBlock[];
  commitments?: PlannerCommitment[];
  scheduled_minutes?: number;
  commitment_minutes?: number;
  available_minutes?: number;
  free_minutes?: number;
};
type PlannerInterpretation = {
  text: string;
  mode: "day" | "week" | "goal" | null;
  start_date: string | null;
  horizon_days: number | null;
  energy_mode: "light" | "normal" | "intense";
  rebalance_requested: boolean;
  from_now: boolean;
  commitments: Array<{ title: string; date: string; start_time: string | null; end_time: string; commitment_type: string }>;
  focus_requests: Array<{ title: string; minutes: number; source_text: string }>;
  priority_terms: string[];
  assumptions: string[];
  understood: boolean;
};

type SmartPlan = {
  id?: number;
  title: string;
  mode: "day" | "week" | "goal";
  start_date: string;
  end_date: string;
  horizon_days?: number;
  project_id?: number | null;
  supersedes_plan_id?: number | null;
  rebalanced_from_plan_id?: number | null;
  status?: string;
  request_text: string | null;
  summary: string;
  working_start: string;
  working_end: string;
  break_minutes: number;
  available_minutes: number;
  scheduled_minutes: number;
  candidate_minutes?: number;
  commitment_minutes?: number;
  energy_mode?: "light" | "normal" | "intense";
  energy_reserve_minutes?: number;
  interpretation?: PlannerInterpretation | null;
  overload_minutes: number;
  deferred_minutes?: number;
  unscheduled_minutes?: number;
  scheduled_tasks?: number;
  candidate_tasks?: number;
  days: PlannerDay[];
  unscheduled?: Array<{
    task_id: number | null;
    title: string;
    minutes: number;
    project_title: string | null;
    importance: string;
    deadline: string | null;
    reason: string;
  }>;
  read_only?: boolean;
  verified_from_state?: boolean;
  confirmation_required?: boolean;
};
type PlannerState = {
  today: string;
  open_task_count: number;
  projects: PlannerProject[];
  active_plan: SmartPlan | null;
  commitments: PlannerCommitment[];
  defaults: { mode: "day" | "week"; working_start: string; working_end: string; break_minutes: number; horizon_days: number };
  verified_from_state: boolean;
};
type PlannerProposal = {
  id: number;
  action_type: string;
  status: string;
  title: string;
  reason: string | null;
  risk_level: string;
  requires_confirmation: boolean;
};

type BlockEdit = { id: number; date: string; start_time: string; end_time: string; locked: boolean; title: string };

function apiMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

function minutesLabel(value: number) {
  const minutes = Math.max(0, Number(value) || 0);
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (!hours) return `${rest}m`;
  if (!rest) return `${hours}h`;
  return `${hours}h ${rest}m`;
}

function dateLabel(value: string) {
  const parsed = new Date(`${value}T12:00:00`);
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(parsed);
}

function PlanningIcon({ type }: { type: "spark" | "calendar" | "clock" | "balance" | "check" | "warning" | "lock" | "pin" | "edit" | "refresh" }) {
  const paths = {
    spark: "m12 2 1.7 4.4L18 8l-4.3 1.6L12 14l-1.7-4.4L6 8l4.3-1.6L12 2Zm6.5 11 .9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9.9-2.1Z",
    calendar: "M5 3v2M19 3v2M4 8h16M5 5h14a1 1 0 0 1 1 1v14H4V6a1 1 0 0 1 1-1Zm3 7h3v3H8v-3Z",
    clock: "M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Zm1 11h4v-2h-3V6h-2v7h1Z",
    balance: "M4 19h16M7 16l5-11 5 11M9 12h6",
    check: "m5 12 4 4L19 6",
    warning: "M12 3 2 21h20L12 3Zm0 6v5m0 3v1",
    lock: "M7 10V7a5 5 0 0 1 10 0v3h2v11H5V10h2Zm2 0h6V7a3 3 0 0 0-6 0v3Z",
    pin: "m12 2 4 4-2 2 3 5-4 4-5-3-2 2-1-1 2-2-3-5 4-4 2 2Z",
    edit: "m4 16-1 5 5-1L19 9l-4-4L4 16Zm12-13 4 4 1-1a2 2 0 0 0-4-4l-1 1Z",
    refresh: "M20 6v6h-6l2.3-2.3A6 6 0 1 0 17 16h2a8 8 0 1 1-1.3-7.7L20 6Z",
  } as const;
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={paths[type]} /></svg>;
}

function StateBadge({ state }: { state?: PlannerBlock["state"] }) {
  if (!state) return null;
  const label = state === "completed" ? "Done" : state === "missed" ? "Missed" : state === "current" ? "Now" : "Upcoming";
  return <span className={`planner-state-badge state-${state}`}>{label}</span>;
}

function PlanTimeline({ plan, editable, onEdit }: { plan: SmartPlan; editable: boolean; onEdit: (block: PlannerBlock) => void }) {
  const visibleDays = plan.days.filter((day) => day.blocks.length || day.commitments?.length || plan.mode === "day");
  return <div className="planner-timeline">
    {visibleDays.map((day) => {
      const entries = [
        ...(day.commitments || []).map((item) => ({ kind: "commitment" as const, time: item.start_time, item })),
        ...day.blocks.map((item) => ({ kind: "block" as const, time: item.start_time, item })),
      ].sort((a, b) => a.time.localeCompare(b.time));
      return <section className="planner-day" key={day.date}>
        <header className="planner-day-heading">
          <div><span>{day.label}</span><strong>{dateLabel(day.date)}</strong></div>
          <small>{typeof day.scheduled_minutes === "number" ? `${minutesLabel(day.scheduled_minutes)} planned` : ""}{typeof day.commitment_minutes === "number" && day.commitment_minutes > 0 ? ` · ${minutesLabel(day.commitment_minutes)} fixed` : ""}</small>
        </header>
        <div className="planner-day-line">
          {entries.length ? entries.map((entry) => {
            if (entry.kind === "commitment") return <article className="planner-block planner-commitment" key={`commitment-${entry.item.id}`}>
              <div className="planner-block-time"><strong>{entry.item.start_time}</strong><span>{entry.item.end_time}</span></div>
              <div className="planner-block-rail"><i /></div>
              <div className="planner-block-card">
                <div className="planner-block-top"><span className="planner-fixed-label"><PlanningIcon type="pin" /> Fixed · {entry.item.commitment_type}</span><small>{entry.item.source === "academic" ? "Academic schedule" : "Commitment"}</small></div>
                <h3>{entry.item.title}</h3>
                {entry.item.notes ? <p>{entry.item.notes}</p> : null}
              </div>
            </article>;

            const block = entry.item;
            if (block.block_type === "inferred_commitment") return <article className="planner-block planner-commitment planner-inferred-commitment" key={`${block.date}-${block.start_time}-${block.title}-${block.sort_order}`}>
              <div className="planner-block-time"><strong>{block.start_time}</strong><span>{block.end_time}</span></div>
              <div className="planner-block-rail"><i /></div>
              <div className="planner-block-card">
                <div className="planner-block-top"><span className="planner-fixed-label"><PlanningIcon type="spark" /> Understood from prompt</span><span className="planner-lock-badge"><PlanningIcon type="lock" /> Locked</span></div>
                <h3>{block.title}</h3>
                <p>{block.rationale || "V-SPACE treated this as unavailable time from your planning request."}</p>
                {editable && block.id ? <button className="planner-block-edit" type="button" onClick={() => onEdit(block)}><PlanningIcon type="edit" /> Adjust interpreted time</button> : null}
              </div>
            </article>;

            return <article className={`planner-block planner-task-state-${block.state || "upcoming"} ${block.block_type === "focus" ? "planner-focus-block" : ""}`} key={`${block.date}-${block.start_time}-${block.task_id}-${block.sort_order}`}>
              <div className="planner-block-time"><strong>{block.start_time}</strong><span>{block.end_time}</span></div>
              <div className="planner-block-rail"><i /></div>
              <div className="planner-block-card">
                <div className="planner-block-top">
                  <span className={`planner-priority priority-${(block.importance || "medium").toLowerCase()}`}>{block.block_type === "focus" ? "Focus" : block.importance || "Medium"}</span>
                  <div className="planner-block-badges"><StateBadge state={block.state} />{block.locked ? <span className="planner-lock-badge"><PlanningIcon type="lock" /> Locked</span> : null}<small>{minutesLabel(block.minutes)}</small></div>
                </div>
                <h3>{block.title}</h3>
                <div className="planner-block-meta">
                  <span>{block.block_type === "focus" ? "Requested focus time" : block.project_title || "General workspace"}</span>
                  {block.deadline ? <span>Due {dateLabel(block.deadline)}</span> : null}
                </div>
                {block.rationale ? <p>{block.rationale}</p> : null}
                {editable && block.id && block.state !== "completed" ? <button className="planner-block-edit" type="button" onClick={() => onEdit(block)}><PlanningIcon type="edit" /> Edit time & lock</button> : null}
              </div>
            </article>;
          }) : <div className="planner-open-day"><span>Open capacity</span><p>No task blocks or fixed commitments are scheduled for this day.</p></div>}
        </div>
      </section>;
    })}
  </div>;
}

export function SmartPlannerPage() {
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const [mode, setMode] = useState<"day" | "week" | "goal">("day");
  const [horizonDays, setHorizonDays] = useState(7);
  const [startDate, setStartDate] = useState(today);
  const [workingStart, setWorkingStart] = useState("09:00");
  const [workingEnd, setWorkingEnd] = useState("17:00");
  const [breakMinutes, setBreakMinutes] = useState(15);
  const [projectId, setProjectId] = useState("");
  const [requestText, setRequestText] = useState("");
  const [preview, setPreview] = useState<SmartPlan | null>(null);
  const [proposal, setProposal] = useState<PlannerProposal | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCommitmentForm, setShowCommitmentForm] = useState(false);
  const [commitmentTitle, setCommitmentTitle] = useState("");
  const [commitmentDate, setCommitmentDate] = useState(today);
  const [commitmentStart, setCommitmentStart] = useState("12:00");
  const [commitmentEnd, setCommitmentEnd] = useState("13:00");
  const [commitmentType, setCommitmentType] = useState("meeting");
  const [editingBlock, setEditingBlock] = useState<BlockEdit | null>(null);

  const stateQuery = useQuery({
    queryKey: ["smart-planner", startDate],
    queryFn: () => apiGet<{ planner: PlannerState }>(`/api/v1/planner?date=${encodeURIComponent(startDate)}`),
  });

  const payload = () => ({
    mode,
    start_date: startDate,
    horizon_days: horizonDays,
    working_start: workingStart,
    working_end: workingEnd,
    break_minutes: breakMinutes,
    project_id: projectId || null,
    request_text: requestText.trim() || null,
  });

  const previewMutation = useMutation({
    mutationFn: () => requestText.trim()
      ? apiPost<{ preview: SmartPlan; interpretation?: PlannerInterpretation }>("/api/v1/planner/natural-preview", payload())
      : apiPost<{ preview: SmartPlan }>("/api/v1/planner/preview", payload()),
    onSuccess: ({ preview: next }) => {
      setPreview(next);
      setMode(next.mode);
      setStartDate(next.start_date);
      if (next.mode === "goal" && next.horizon_days) setHorizonDays(next.horizon_days);
      if (next.project_id) setProjectId(String(next.project_id));
      setProposal(null);
      setMessage(null);
      setError(null);
    },
    onError: (value) => setError(apiMessage(value, "V-SPACE could not build this plan.")),
  });

  const proposalMutation = useMutation({
    mutationFn: () => {
      if (preview?.interpretation) {
        return apiPost<{ proposal: PlannerProposal }>("/api/v1/planner/natural-proposals", payload());
      }
      if (preview?.rebalanced_from_plan_id) {
        return apiPost<{ proposal: PlannerProposal }>(`/api/v1/planner/plans/${preview.rebalanced_from_plan_id}/rebalance-proposals`, { from_date: preview.start_date });
      }
      return apiPost<{ proposal: PlannerProposal }>("/api/v1/planner/proposals", payload());
    },
    onSuccess: ({ proposal: next }) => {
      setProposal(next);
      setError(null);
      setMessage("Review the plan once more, then confirm it to save the schedule.");
    },
    onError: (value) => setError(apiMessage(value, "V-SPACE could not prepare this plan for confirmation.")),
  });

  const confirmMutation = useMutation({
    mutationFn: (proposalId: number) => apiPost<{ proposal: PlannerProposal; changed: boolean }>(`/api/v1/intelligence/action-proposals/${proposalId}/confirm`, {}),
    onSuccess: async () => {
      setProposal(null);
      setPreview(null);
      setMessage("Plan accepted. Your Smart Planner schedule is now saved.");
      setError(null);
      await stateQuery.refetch();
    },
    onError: (value) => setError(apiMessage(value, "V-SPACE could not save the confirmed plan.")),
  });

  const dismissMutation = useMutation({
    mutationFn: (proposalId: number) => apiPost<{ proposal: PlannerProposal; changed: boolean }>(`/api/v1/intelligence/action-proposals/${proposalId}/dismiss`, {}),
    onSuccess: () => {
      setProposal(null);
      setMessage("Plan confirmation dismissed. Nothing changed in your workspace.");
    },
    onError: (value) => setError(apiMessage(value, "V-SPACE could not dismiss the plan proposal.")),
  });

  const rebalanceMutation = useMutation({
    mutationFn: (planId: number) => apiPost<{ preview: SmartPlan }>(`/api/v1/planner/plans/${planId}/rebalance-preview`, { from_date: today }),
    onSuccess: ({ preview: next }) => {
      setPreview(next);
      setProposal(null);
      setMessage("Rebalanced preview ready. Locked blocks stayed in place; nothing has been saved yet.");
      setError(null);
    },
    onError: (value) => setError(apiMessage(value, "V-SPACE could not rebalance the remaining plan.")),
  });

  const createCommitmentMutation = useMutation({
    mutationFn: () => apiPost<{ commitment: PlannerCommitment }>("/api/v1/planner/commitments", {
      title: commitmentTitle,
      date: commitmentDate,
      start_time: commitmentStart,
      end_time: commitmentEnd,
      commitment_type: commitmentType,
    }),
    onSuccess: async () => {
      setCommitmentTitle("");
      setShowCommitmentForm(false);
      setPreview(null);
      setProposal(null);
      setMessage("Fixed commitment saved. Regenerate the plan to schedule around it.");
      setError(null);
      await stateQuery.refetch();
    },
    onError: (value) => setError(apiMessage(value, "V-SPACE could not save that commitment.")),
  });

  const deleteCommitmentMutation = useMutation({
    mutationFn: (id: number) => apiDelete<{ deleted: boolean }>(`/api/v1/planner/commitments/${id}`),
    onSuccess: async () => {
      setPreview(null);
      setProposal(null);
      setMessage("Commitment removed. Regenerate to use the newly free time.");
      await stateQuery.refetch();
    },
    onError: (value) => setError(apiMessage(value, "V-SPACE could not remove that commitment.")),
  });

  const updateBlockMutation = useMutation({
    mutationFn: (edit: BlockEdit) => {
      const planId = stateQuery.data?.planner.active_plan?.id;
      if (!planId) throw new Error("No accepted plan");
      return apiPatch<{ plan: SmartPlan }>(`/api/v1/planner/plans/${planId}/blocks/${edit.id}`, {
        date: edit.date,
        start_time: edit.start_time,
        end_time: edit.end_time,
        locked: edit.locked,
      });
    },
    onSuccess: async () => {
      setEditingBlock(null);
      setMessage("Planner block updated. Locked blocks will stay fixed during rebalancing.");
      setError(null);
      await stateQuery.refetch();
    },
    onError: (value) => setError(apiMessage(value, "V-SPACE could not update that planner block.")),
  });

  if (stateQuery.isPending) return <PageState title="Opening Smart Planner" text="Reading your tasks, commitments and planning state…" />;
  if (stateQuery.isError || !stateQuery.data) return <PageState title="Smart Planner unavailable" text="V-SPACE could not load your planning workspace." error retry={() => stateQuery.refetch()} />;

  const planner = stateQuery.data.planner;
  const shownPlan = preview || planner.active_plan;
  const accepted = !preview && !!planner.active_plan;
  const activePlan = planner.active_plan;
  const visibleCommitments = planner.commitments.filter((item) => item.date >= startDate && item.date <= (shownPlan?.end_date || startDate));

  function chooseMode(next: "day" | "week" | "goal") {
    setMode(next);
    setPreview(null);
    setProposal(null);
    setMessage(null);
  }

  function editBlock(block: PlannerBlock) {
    if (!block.id) return;
    setEditingBlock({ id: block.id, date: block.date, start_time: block.start_time, end_time: block.end_time, locked: !!block.locked, title: block.title });
  }

  return <section className="smart-planner-page">
    <header className="planner-hero">
      <div>
        <span className="planner-eyebrow"><PlanningIcon type="spark" /> V-SPACE intelligence</span>
        <h1>Smart Planner</h1>
        <p>Build a realistic schedule around your real commitments. Lock what cannot move, then let V-SPACE rebalance the rest when your day changes.</p>
      </div>
      <div className="planner-mode-switch" aria-label="Planner mode">
        <button type="button" className={mode === "day" ? "active" : ""} onClick={() => chooseMode("day")}>Day</button>
        <button type="button" className={mode === "week" ? "active" : ""} onClick={() => chooseMode("week")}>Week</button>
        <button type="button" className={mode === "goal" ? "active" : ""} onClick={() => chooseMode("goal")}>Goal</button>
      </div>
    </header>

    <section className="planner-command-card">
      <div className="planner-command-icon"><PlanningIcon type="spark" /></div>
      <label>
        <span>{mode === "goal" ? "What goal should V-SPACE move forward?" : "What do you want to accomplish?"}</span>
        <input value={requestText} maxLength={600} onChange={(event) => { setRequestText(event.target.value); setPreview(null); setProposal(null); }} placeholder={mode === "day" ? "Example: Tomorrow I have university until 2, then 3 hours for V-SPACE and 90 minutes for calculus" : mode === "week" ? "Example: Plan my week around classes and make sure I finish deployment before Friday" : "Example: Get V-SPACE V1 ready in 10 days"} />
      </label>
      <button type="button" className="planner-generate-button" onClick={() => previewMutation.mutate()} disabled={previewMutation.isPending}>
        {previewMutation.isPending ? "Planning…" : "Build plan"}<span>→</span>
      </button>
    </section>

    {error ? <div className="planner-alert error" role="alert">{error}</div> : null}
    {message ? <div className="planner-alert success" role="status">{message}</div> : null}

    {preview?.interpretation?.understood ? <section className="planner-understood-card">
      <div className="planner-understood-heading"><span><PlanningIcon type="spark" /> V-SPACE understood</span><strong>Review the interpretation before you accept the plan.</strong></div>
      <div className="planner-understood-chips">
        {preview.interpretation.start_date ? <span><PlanningIcon type="calendar" /> {dateLabel(preview.interpretation.start_date)}</span> : null}
        {preview.interpretation.mode ? <span>{preview.interpretation.mode === "goal" ? `${preview.interpretation.horizon_days || preview.horizon_days || 7}-day goal` : `${preview.interpretation.mode} plan`}</span> : null}
        {preview.interpretation.energy_mode !== "normal" ? <span>{preview.interpretation.energy_mode === "light" ? "Lighter day" : "Intense day"}</span> : null}
        {preview.interpretation.commitments.length ? <span><PlanningIcon type="pin" /> {preview.interpretation.commitments.length} time constraint{preview.interpretation.commitments.length === 1 ? "" : "s"}</span> : null}
        {preview.interpretation.focus_requests.length ? <span><PlanningIcon type="clock" /> {preview.interpretation.focus_requests.length} focus request{preview.interpretation.focus_requests.length === 1 ? "" : "s"}</span> : null}
        {preview.interpretation.rebalance_requested ? <span><PlanningIcon type="refresh" /> Rebalance current plan</span> : null}
      </div>
      {preview.interpretation.assumptions.length ? <ul>{preview.interpretation.assumptions.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul> : null}
    </section> : null}

    <div className="planner-layout">
      <main className="planner-main">
        <section className="planner-summary-grid planner-summary-grid-four">
          <article><span><PlanningIcon type="calendar" />Plan</span><strong>{shownPlan ? `${dateLabel(shownPlan.start_date)}${shownPlan.end_date !== shownPlan.start_date ? ` – ${dateLabel(shownPlan.end_date)}` : ""}` : dateLabel(startDate)}</strong><small>{preview ? "Fresh preview" : accepted ? "Accepted schedule" : "Ready to plan"}</small></article>
          <article><span><PlanningIcon type="clock" />Scheduled</span><strong>{shownPlan ? minutesLabel(shownPlan.scheduled_minutes) : "—"}</strong><small>{shownPlan ? `${shownPlan.scheduled_tasks ?? shownPlan.days.reduce((sum, day) => sum + day.blocks.length, 0)} task blocks` : `${planner.open_task_count} open tasks available`}</small></article>
          <article><span><PlanningIcon type="pin" />Fixed time</span><strong>{shownPlan ? minutesLabel(shownPlan.commitment_minutes || 0) : visibleCommitments.length ? `${visibleCommitments.length} items` : "None"}</strong><small>{visibleCommitments.length ? `${visibleCommitments.filter((item) => item.source === "academic").length} from academic schedule` : "Add classes, meetings or appointments."}</small></article>
          <article className={shownPlan?.overload_minutes ? "warning" : ""}><span><PlanningIcon type="balance" />Workload</span><strong>{shownPlan ? (shownPlan.overload_minutes ? `${minutesLabel(shownPlan.overload_minutes)} over` : shownPlan.energy_mode === "light" ? "Light" : "Fits") : "—"}</strong><small>{shownPlan?.overload_minutes ? "Work stays unscheduled instead of overfilling the day." : shownPlan?.energy_mode === "light" ? `${minutesLabel(shownPlan.energy_reserve_minutes || 0)} intentionally reserved` : "Capacity stays realistic."}</small></article>
        </section>

        <section className="planner-plan-panel">
          <header className="planner-panel-heading">
            <div><span>{accepted ? "Accepted plan" : preview?.rebalanced_from_plan_id ? "Rebalanced preview" : preview ? "Proposed plan" : "Timeline"}</span><h2>{shownPlan?.title || "Build your first smart plan"}</h2></div>
            {shownPlan?.verified_from_state || accepted ? <span className="planner-trust-badge"><i />Workspace state</span> : null}
          </header>
          {shownPlan ? <>
            <div className="planner-plan-summary"><PlanningIcon type={shownPlan.overload_minutes ? "warning" : "check"} /><p>{shownPlan.summary}</p></div>
            <PlanTimeline plan={shownPlan} editable={accepted} onEdit={editBlock} />
          </> : <div className="planner-empty-state"><div className="planner-empty-orb"><PlanningIcon type="spark" /></div><h3>Your workload is ready.</h3><p>Add fixed commitments if you need them, choose your working window and build a plan. Previewing never changes anything in V-SPACE.</p><button type="button" onClick={() => previewMutation.mutate()}>Plan {mode === "day" ? "my day" : mode === "week" ? "my week" : "my goal"}</button></div>}
        </section>

        {preview?.unscheduled?.length ? <section className="planner-unscheduled-panel">
          <header><div><span>Capacity check</span><h2>{preview.deferred_minutes && !preview.overload_minutes ? "V-SPACE kept the day lighter" : "Not everything fits"}</h2></div><strong>{minutesLabel(preview.unscheduled_minutes ?? preview.overload_minutes)} unscheduled</strong></header>
          <p>These tasks remain outside the plan. V-SPACE will never hide an overloaded schedule by pretending more work fits.</p>
          <div className="planner-unscheduled-list">{preview.unscheduled.map((item) => <article key={item.task_id}><div><strong>{item.title}</strong><span>{item.project_title || "General workspace"}{item.deadline ? ` · Due ${dateLabel(item.deadline)}` : ""}</span></div><small>{minutesLabel(item.minutes)}</small></article>)}</div>
        </section> : null}
      </main>

      <aside className="planner-sidebar">
        <section className="planner-settings-card">
          <div className="planner-card-heading"><span>Planning controls</span><h2>Shape the plan</h2><p>Exact time math is deterministic. Fixed commitments and locked blocks are treated as unavailable time.</p></div>
          <label><span>Start date</span><input type="date" value={startDate} onChange={(event) => { setStartDate(event.target.value); setCommitmentDate(event.target.value); setPreview(null); setProposal(null); }} /></label>
          <label><span>Project</span><select value={projectId} onChange={(event) => { setProjectId(event.target.value); setPreview(null); setProposal(null); }}><option value="">All open work</option>{planner.projects.map((project) => <option key={project.id} value={project.id}>{project.title}</option>)}</select></label>
          {mode === "goal" ? <label><span>Goal horizon</span><select value={horizonDays} onChange={(event) => setHorizonDays(Number(event.target.value))}>{[3, 5, 7, 10, 14].map((days) => <option key={days} value={days}>{days} days</option>)}</select></label> : null}
          <div className="planner-time-grid"><label><span>Start</span><input type="time" value={workingStart} onChange={(event) => setWorkingStart(event.target.value)} /></label><label><span>Finish</span><input type="time" value={workingEnd} onChange={(event) => setWorkingEnd(event.target.value)} /></label></div>
          <label><span>Break between blocks</span><select value={breakMinutes} onChange={(event) => setBreakMinutes(Number(event.target.value))}><option value={0}>No automatic break</option><option value={5}>5 minutes</option><option value={10}>10 minutes</option><option value={15}>15 minutes</option><option value={30}>30 minutes</option></select></label>
          <button type="button" className="planner-secondary-action" onClick={() => previewMutation.mutate()} disabled={previewMutation.isPending}>Regenerate plan</button>
        </section>

        <section className="planner-settings-card planner-commitment-card">
          <div className="planner-card-heading"><span>Fixed commitments</span><h2>Protect your real time</h2><p>Classes, meetings and timed assessments block the planner from scheduling over them.</p></div>
          <div className="planner-commitment-list">
            {planner.commitments.filter((item) => item.date >= startDate).slice(0, 6).map((item) => <article key={String(item.id)}>
              <div><strong>{item.title}</strong><span>{dateLabel(item.date)} · {item.start_time}–{item.end_time}</span><small>{item.source === "academic" ? `Academic${item.module_title ? ` · ${item.module_title}` : ""}` : item.commitment_type}</small></div>
              {item.editable && typeof item.id === "number" ? <button type="button" aria-label={`Remove ${item.title}`} onClick={() => deleteCommitmentMutation.mutate(item.id as number)}>×</button> : <i className="planner-readonly-dot" title="Synced from academic schedule" />}
            </article>)}
            {!planner.commitments.filter((item) => item.date >= startDate).length ? <p className="planner-no-commitments">No fixed commitments in the next two weeks.</p> : null}
          </div>
          {!showCommitmentForm ? <button type="button" className="planner-secondary-action" onClick={() => setShowCommitmentForm(true)}>+ Add commitment</button> : <div className="planner-commitment-form">
            <label><span>Title</span><input value={commitmentTitle} onChange={(event) => setCommitmentTitle(event.target.value)} placeholder="Example: University class" /></label>
            <label><span>Type</span><select value={commitmentType} onChange={(event) => setCommitmentType(event.target.value)}><option value="class">Class</option><option value="meeting">Meeting</option><option value="exam">Exam</option><option value="appointment">Appointment</option><option value="personal">Personal</option><option value="other">Other</option></select></label>
            <label><span>Date</span><input type="date" value={commitmentDate} onChange={(event) => setCommitmentDate(event.target.value)} /></label>
            <div className="planner-time-grid"><label><span>Start</span><input type="time" value={commitmentStart} onChange={(event) => setCommitmentStart(event.target.value)} /></label><label><span>Finish</span><input type="time" value={commitmentEnd} onChange={(event) => setCommitmentEnd(event.target.value)} /></label></div>
            <button type="button" className="planner-primary-action" disabled={createCommitmentMutation.isPending || !commitmentTitle.trim()} onClick={() => createCommitmentMutation.mutate()}>{createCommitmentMutation.isPending ? "Saving…" : "Save commitment"}</button>
            <button type="button" className="planner-text-action" onClick={() => setShowCommitmentForm(false)}>Cancel</button>
          </div>}
        </section>

        {editingBlock ? <section className="planner-settings-card planner-edit-card">
          <div className="planner-card-heading"><span>Manual adjustment</span><h2>{editingBlock.title}</h2><p>Explicit edits are deterministic. Lock the block if V-SPACE should preserve it during rebalancing.</p></div>
          <label><span>Date</span><input type="date" value={editingBlock.date} onChange={(event) => setEditingBlock({ ...editingBlock, date: event.target.value })} /></label>
          <div className="planner-time-grid"><label><span>Start</span><input type="time" value={editingBlock.start_time} onChange={(event) => setEditingBlock({ ...editingBlock, start_time: event.target.value })} /></label><label><span>Finish</span><input type="time" value={editingBlock.end_time} onChange={(event) => setEditingBlock({ ...editingBlock, end_time: event.target.value })} /></label></div>
          <label className="planner-lock-toggle"><input type="checkbox" checked={editingBlock.locked} onChange={(event) => setEditingBlock({ ...editingBlock, locked: event.target.checked })} /><span><PlanningIcon type="lock" /> Keep this block locked during rebalancing</span></label>
          <button type="button" className="planner-primary-action" disabled={updateBlockMutation.isPending} onClick={() => updateBlockMutation.mutate(editingBlock)}>{updateBlockMutation.isPending ? "Saving…" : "Save adjustment"}</button>
          <button type="button" className="planner-text-action" onClick={() => setEditingBlock(null)}>Cancel</button>
        </section> : null}

        {preview ? <section className="planner-decision-card">
          <div className="planner-decision-mark"><PlanningIcon type="check" /></div>
          <span>{preview.rebalanced_from_plan_id ? "Rebalance ready" : "Ready for review"}</span>
          <h2>{preview.rebalanced_from_plan_id ? "Replace the remaining plan?" : "Like this plan?"}</h2>
          <p>Preparing creates a confirmation proposal only. The accepted schedule changes only after you explicitly confirm it.</p>
          {!proposal ? <button type="button" className="planner-primary-action" onClick={() => proposalMutation.mutate()} disabled={proposalMutation.isPending}>{proposalMutation.isPending ? "Preparing…" : "Prepare to accept"}</button> : <>
            <div className="planner-confirmation-box"><strong>Confirmation required</strong><p>{proposal.reason || "Review the proposed schedule before saving it."}</p></div>
            <button type="button" className="planner-primary-action" onClick={() => confirmMutation.mutate(proposal.id)} disabled={confirmMutation.isPending}>{confirmMutation.isPending ? "Saving…" : "Accept plan"}</button>
            <button type="button" className="planner-text-action" onClick={() => dismissMutation.mutate(proposal.id)} disabled={dismissMutation.isPending}>Dismiss</button>
          </>}
        </section> : activePlan?.id ? <section className="planner-decision-card accepted"><div className="planner-decision-mark"><PlanningIcon type="check" /></div><span>Current schedule</span><h2>Plan accepted</h2><p>Completed tasks update automatically. If something slips, rebalance only the remaining schedule while locked blocks stay fixed.</p><button type="button" className="planner-primary-action planner-rebalance-action" onClick={() => rebalanceMutation.mutate(activePlan.id!)} disabled={rebalanceMutation.isPending}><PlanningIcon type="refresh" /> {rebalanceMutation.isPending ? "Rebalancing…" : "Rebalance remaining"}</button><button type="button" className="planner-secondary-action" onClick={() => { setPreview(null); setProposal(null); previewMutation.mutate(); }}>Build new plan</button></section> : null}
      </aside>
    </div>
  </section>;
}
