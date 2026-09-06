import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiDelete, apiGet, apiPatch, apiPost } from "../api/client";
import type {
  AutomationRegistryData,
  AutomationRun,
  AutomationTemplate,
  AutomationVisualTemplate,
  DocumentCollectionSummary,
  DocumentSummary,
  IntelligenceActionProposal,
  LearningModule,
  LifeOSAutomation,
  ProjectListData,
} from "../api/types";
import { PageHeader, PageState } from "../components/NativeUi";
import { fetchProjects } from "../features/projects/api";
import { VisualAutomationFlowBuilder } from "../features/automations/VisualAutomationFlowBuilder";

function fmt(value: string | null) {
  if (!value) return "Event-triggered";
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function triggerLabel(item: LifeOSAutomation) {
  const config = item.trigger.config;
  if (item.trigger.type === "manual") return "When I click Run now";
  if (item.trigger.type === "schedule_daily") {
    return `Daily · ${String(config.hour ?? 8).padStart(2, "0")}:${String(config.minute ?? 0).padStart(2, "0")}`;
  }
  if (item.trigger.type === "schedule_weekly") {
    const labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    return `${labels[Number(config.weekday ?? 0)] ?? "Weekly"} · ${String(config.hour ?? 8).padStart(2, "0")}:${String(config.minute ?? 0).padStart(2, "0")}`;
  }
  const eventType = String(config.event_type || "");
  const eventLabels: Record<string, string> = {
    "task.overdue": "When a task becomes overdue",
    "task.blocked": "When a task becomes blocked",
    "project.overdue": "When a project becomes overdue",
    "project.deadline_approaching": "When a project deadline is approaching",
    "document.intelligence_stale": "When a document becomes stale",
    "document.version_changed": "When a document changes",
  };
  return eventLabels[eventType] ?? (eventType ? `When ${eventType.replace(/\./g, " ")}` : "When a LifeOS event happens");
}

const FRIENDLY_FLOW_STEPS: Record<string, string> = {
  "trigger.schedule_daily": "Every day",
  "trigger.schedule_weekly": "Every week",
  "trigger.manual_run": "When I click Run now",
  "trigger.task_overdue": "When a task becomes overdue",
  "trigger.task_blocked": "When a task becomes blocked",
  "trigger.project_overdue": "When a project becomes overdue",
  "trigger.project_deadline_approaching": "When a project deadline is approaching",
  "trigger.document_stale": "When a document becomes stale",
  "trigger.document_version_changed": "When a document changes",
  "context.all_lifeos": "my LifeOS workspace",
  "context.project": "the selected project",
  "context.document": "the selected document",
  "context.module": "the selected module",
  "context.collection": "the selected collection",
  "context.recent_activity": "recent activity",
  "intelligence.today_briefing": "Build my daily briefing",
  "intelligence.portfolio_review": "Review my workspace",
  "intelligence.project_review": "Review project",
  "intelligence.detect_risks": "Find important risks",
  "intelligence.find_unhandled_findings": "Find unhandled findings",
  "intelligence.event_context_review": "Understand what happened",
  "intelligence.review_document": "Review the knowledge",
  "intelligence.rank_priorities": "Rank what matters most",
  "intelligence.what_changed": "Tell me what changed",
  "intelligence.ask_lifeos": "Answer my custom question",
  "condition.attention_needed": "Only continue if attention is needed",
  "condition.results_found": "Only continue if useful results were found",
  "output.notify_me": "Notify me",
  "output.save_review_result": "Save result in history",
  "output.suggest_action": "Suggest what I should do next",
  "proposal.create_task": "Ask me before creating a task",
  "proposal.save_note": "Ask me before saving a note",
  "proposal.refresh_analysis": "Ask me before refreshing analysis",
};

function friendlyFlowStep(step: { node_type: string; label: string }) {
  return FRIENDLY_FLOW_STEPS[step.node_type] ?? step.label;
}

function lowerFirst(value: string) {
  return value ? `${value.charAt(0).toLowerCase()}${value.slice(1)}` : value;
}

function automationSentence(item: LifeOSAutomation, registry: AutomationRegistryData) {
  const config = item.trigger.config;
  const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const when = item.trigger.type === "schedule_daily"
    ? `Every day at ${String(config.hour ?? 8).padStart(2, "0")}:${String(config.minute ?? 0).padStart(2, "0")}`
    : item.trigger.type === "schedule_weekly"
      ? `Every ${weekdays[Number(config.weekday ?? 0)] ?? "week"} at ${String(config.hour ?? 8).padStart(2, "0")}:${String(config.minute ?? 0).padStart(2, "0")}`
      : triggerLabel(item);
  const steps = item.compiled_plan?.steps ?? [];
  if (!steps.length) return `${when}, ask LifeOS to ${lowerFirst(actionLabel(registry, item.action.type))}.`;

  const contexts = steps.filter((step) => step.category === "context").map((step) => lowerFirst(friendlyFlowStep(step)));
  const intelligence = steps.filter((step) => step.category === "intelligence").map((step) => lowerFirst(friendlyFlowStep(step)));
  const conditions = steps.filter((step) => step.category === "condition").map((step) => lowerFirst(friendlyFlowStep(step)));
  const outcomes = steps.filter((step) => step.category === "output" || step.category === "proposal").map((step) => lowerFirst(friendlyFlowStep(step)));

  let sentence = when;
  if (contexts.length) sentence += `, look at ${contexts.join(" and ")}`;
  if (intelligence.length) sentence += `, ask LifeOS to ${intelligence.join(", then ")}`;
  if (conditions.length) sentence += `, ${conditions.join(", then ")}`;
  if (outcomes.length) sentence += `, then ${outcomes.join(", then ")}`;
  return `${sentence}.`;
}

function actionLabel(registry: AutomationRegistryData, type: string) {
  return registry.actions.find((item) => item.type === type)?.label ?? type.replace(/_/g, " ");
}

type VisualNodeRun = {
  node_id?: string;
  label?: string;
  capability?: string;
  status?: string;
  duration_ms?: number;
  summary?: string;
  error?: string;
  skip_reason?: string;
  result?: Record<string, unknown>;
};

type VisualRunTrace = {
  status?: string;
  error?: string;
  completed_nodes?: number;
  failed_nodes?: number;
  skipped_nodes?: number;
  node_runs?: VisualNodeRun[];
};

function visualTrace(run: AutomationRun): VisualRunTrace | null {
  return visualTraceFromOutput(run.output, run.status);
}

function visualTraceFromOutput(output: Record<string, unknown>, status?: string): VisualRunTrace | null {
  const nested = output.visual_flow;
  if (nested && typeof nested === "object") return nested as VisualRunTrace;
  const rootTrace = output.flow_trace;
  if (Array.isArray(rootTrace)) {
    return {
      status,
      node_runs: rootTrace as VisualRunTrace["node_runs"],
      error: String(output.halt_reason || output.summary || "") || undefined,
    };
  }
  return null;
}

function traceCounts(trace: VisualRunTrace | null) {
  const nodes = trace?.node_runs ?? [];
  const completed = trace?.completed_nodes ?? nodes.filter((node) => node.status === "succeeded").length;
  const skipped = trace?.skipped_nodes ?? nodes.filter((node) => node.status === "skipped").length;
  const failed = trace?.failed_nodes ?? nodes.filter((node) => node.status === "failed").length;
  return { completed, skipped, failed };
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function resultText(result: Record<string, unknown> | undefined) {
  if (!result) return null;
  const answer = typeof result.answer === "string" ? result.answer.trim() : "";
  if (answer) return answer;
  const summary = typeof result.summary === "string" ? result.summary.trim() : "";
  return summary || null;
}

function resultTitle(result: Record<string, unknown> | undefined, fallback: string) {
  const title = result && typeof result.title === "string" ? result.title.trim() : "";
  return title || fallback;
}

function resultPriorities(result: Record<string, unknown> | undefined) {
  if (!result || !Array.isArray(result.priorities)) return [] as Record<string, unknown>[];
  return result.priorities.map(recordValue).filter((item): item is Record<string, unknown> => Boolean(item)).slice(0, 3);
}

function proposalDescription(result: Record<string, unknown> | undefined) {
  const proposal = recordValue(result?.proposal);
  if (!proposal) return null;
  const actionType = typeof proposal.action_type === "string" ? proposal.action_type.replace(/_/g, " ") : "workspace action";
  const title = typeof proposal.title === "string" ? proposal.title.trim() : "";
  const status = typeof proposal.status === "string" ? proposal.status : "";
  return `${actionType}${title ? ` · ${title}` : ""}${status ? ` · ${status}` : ""}`;
}

function nodeHasDetails(node: VisualNodeRun) {
  const result = node.result;
  return Boolean(
    node.error ||
    node.skip_reason ||
    resultText(result) ||
    resultPriorities(result).length ||
    recordValue(result?.proposal) ||
    typeof result?.condition_passed === "boolean"
  );
}

function NodeResultDetails({ node }: { node: VisualNodeRun }) {
  const result = node.result;
  const text = resultText(result);
  const priorities = resultPriorities(result);
  const proposal = proposalDescription(result);
  const conditionValue = result?.condition_passed;
  const conditionPassed = typeof conditionValue === "boolean" ? conditionValue : null;
  return <div className="automation-node-result-details">
    {text ? <div className="automation-node-result-answer"><span>{node.capability?.startsWith("intelligence.") ? "LifeOS answer" : "Step result"}</span><p>{text}</p></div> : null}
    {priorities.length ? <div className="automation-node-result-priorities"><span>Top findings</span>{priorities.map((priority, index) => <div key={`${node.node_id}-priority-${index}`}><strong>{String(priority.title || `Finding ${index + 1}`)}</strong>{priority.reason ? <p>{String(priority.reason)}</p> : null}{priority.recommended_action ? <small>Next: {String(priority.recommended_action)}</small> : null}</div>)}</div> : null}
    {conditionPassed !== null ? <div className={`automation-node-result-condition ${conditionPassed ? "passed" : "stopped"}`}><strong>{conditionPassed ? "Condition passed" : "Flow stopped here"}</strong><span>{conditionPassed ? "LifeOS continued to the next step." : "Later steps were skipped because this condition was not met."}</span></div> : null}
    {proposal ? <div className="automation-node-result-proposal"><span>Proposed action</span><strong>{proposal}</strong><small>Important workspace changes still require I9 confirmation.</small></div> : null}
    {node.error ? <div className="automation-node-result-error">{node.error}</div> : null}
    {node.skip_reason ? <div className="automation-node-result-skip">{node.skip_reason}</div> : null}
  </div>;
}

function PreviewInsight({ node }: { node: VisualNodeRun }) {
  const result = node.result;
  const answer = resultText(result);
  if (!answer) return null;
  const priorities = resultPriorities(result);
  return <section className="automation-preview-insight">
    <span className="panel-kicker">LifeOS result</span>
    <strong>{resultTitle(result, node.label || "AI result")}</strong>
    <p>{answer}</p>
    {priorities.length ? <details className="automation-preview-evidence"><summary>View evidence and findings ({priorities.length})</summary><div className="automation-preview-findings">{priorities.map((priority, index) => <div key={`preview-finding-${node.node_id}-${index}`}><b>{String(priority.title || `Finding ${index + 1}`)}</b>{priority.reason ? <span>{String(priority.reason)}</span> : null}{priority.recommended_action ? <small>Next: {String(priority.recommended_action)}</small> : null}</div>)}</div></details> : null}
  </section>;
}

function PreviewApproval({ node }: { node: VisualNodeRun }) {
  const proposal = recordValue(node.result?.proposal);
  if (!proposal) return null;
  const actionType = String(proposal.action_type || "");
  const labels: Record<string, string> = {
    create_task: "create a task",
    save_note: "save a note",
    refresh_analysis: "refresh the analysis",
  };
  const action = labels[actionType] ?? (actionType.replace(/_/g, " ") || "make a workspace change");
  const title = String(proposal.title || node.result?.summary || "").trim();
  return <section className="automation-approval-card">
    <div className="automation-approval-icon" aria-hidden="true">✓</div>
    <div>
      <span className="panel-kicker">Needs your approval</span>
      <strong>LifeOS recommends that you {action}</strong>
      {title ? <p>{title}</p> : null}
      <small>Nothing changes during this test. Run the automation to create a real proposal, then you can approve or reject it through I9.</small>
    </div>
    <span className="automation-approval-badge">Preview only</span>
  </section>;
}

function LiveApproval({ proposal, busy, error, onConfirm, onDismiss }: { proposal: IntelligenceActionProposal; busy: boolean; error?: string; onConfirm: () => void; onDismiss: () => void }) {
  const actionLabels: Record<string, string> = { create_task: "Create task", create_note: "Save note", refresh_document_analysis: "Refresh analysis" };
  const payloadTitle = typeof proposal.payload?.title === "string" ? proposal.payload.title : "";
  return <section className={`automation-live-approval status-${proposal.status}`}>
    <div className="automation-approval-icon" aria-hidden="true">✓</div>
    <div className="automation-live-approval-copy">
      <span className="panel-kicker">{proposal.status === "pending" ? "Your decision" : proposal.status === "confirmed" ? "Approved" : proposal.status === "dismissed" ? "Dismissed" : proposal.status === "failed" ? "Action failed" : "Action in progress"}</span>
      <strong>{proposal.title}</strong>
      {proposal.reason ? <p>{proposal.reason}</p> : null}
      {payloadTitle ? <div className="automation-live-approval-preview"><b>{actionLabels[proposal.action_type] ?? proposal.action_type.replace(/_/g, " ")}</b><span>{payloadTitle}</span></div> : null}
      <small>{proposal.status === "pending" ? "LifeOS has not changed your workspace. Confirm only if this is the action you want." : proposal.status === "confirmed" ? "The approved application service completed the workspace change." : proposal.status === "dismissed" ? "Nothing was changed." : "I9 continues to own this action boundary."}</small>
      {proposal.failure_message || error ? <div className="automation-live-approval-error">{proposal.failure_message || error}</div> : null}
      {proposal.status === "pending" ? <div className="automation-live-approval-actions"><button type="button" className="secondary-button" disabled={busy} onClick={onDismiss}>Dismiss</button><button type="button" className="primary-button" disabled={busy} onClick={onConfirm}>{busy ? "Working…" : "Confirm action"}</button></div> : null}
    </div>
  </section>;
}

function TemplateCard({ template, busy, create }: { template: AutomationTemplate; busy: boolean; create: (template: AutomationTemplate) => void }) {
  return <article className="automation-template-card">
    <div className="automation-template-icon">↻</div>
    <div><span className="panel-kicker">Simple automation</span><h3>{template.name}</h3><p>{template.description}</p></div>
    <button type="button" className="secondary-button" disabled={busy} onClick={() => create(template)}>Use this</button>
  </article>;
}

function friendlyVisualTemplateDescription(template: AutomationVisualTemplate) {
  const descriptions: Record<string, string> = {
    visual_morning_focus: "Every morning, look across LifeOS, build your briefing, rank what matters most, and notify you.",
    visual_weekly_review: "Every week, review your workspace and recent activity, explain what changed, and notify you.",
    visual_weekly_risk: "Every week, review your workspace, evaluate important risks, and notify you.",
    visual_quiet_risk_alert: "Check for risk every day, but stay quiet unless the verified result actually needs attention.",
    visual_custom_question: "Run your own read-only Ask LifeOS question on demand and keep the verified answer in run history.",
    visual_project_deadline_watch: "When a project deadline gets close, review that project, find important risks, and notify you.",
    visual_stale_document_review: "When a document becomes stale, review that document with Document Brain and notify you about what needs attention.",
    visual_manual_review: "When you click Run now, review your workspace, rank priorities, and keep the result in run history.",
    visual_i9_note_proposal: "Review your priorities and suggest saving a useful note. LifeOS will still ask you before anything is saved.",
  };
  return descriptions[template.key] ?? template.description;
}

function VisualTemplateCard({ template, busy, create }: { template: AutomationVisualTemplate; busy: boolean; create: (template: AutomationVisualTemplate) => void }) {
  return <article className="automation-template-card visual-recipe-card">
    <div className="automation-template-icon">✦</div>
    <div><span className="panel-kicker">Recommended recipe</span><h3>{template.name}</h3><p>{friendlyVisualTemplateDescription(template)}</p><small>{template.visual_graph.nodes.length} steps · fully editable</small></div>
    <button type="button" className="primary-button" disabled={busy} onClick={() => create(template)}>Use recipe</button>
  </article>;
}

function RunHistory({ runs, loading }: { runs: AutomationRun[]; loading: boolean }) {
  if (loading) return <div className="automation-history-empty">Loading run history…</div>;
  if (!runs.length) return <div className="automation-history-empty">No runs yet. Run or test this automation to see its history here.</div>;
  return <div className="automation-run-history">
    {runs.map((run) => {
      const trace = visualTrace(run);
      const counts = traceCounts(trace);
      const nodeCount = trace?.node_runs?.length ?? 0;
      return <details className={`automation-run-card ${run.status}`} key={run.id}>
        <summary className="automation-run-card-head">
          <div className="automation-run-card-title"><strong>{run.dry_run ? "Test" : "Run"} #{run.id}</strong><span className={`automation-run-status ${run.status}`}>{run.status}</span></div>
          <div className="automation-run-card-quick"><span>{counts.completed} completed{counts.failed ? ` · ${counts.failed} failed` : ""}{counts.skipped ? ` · ${counts.skipped} skipped` : ""}</span><small>{run.started_at ? fmt(run.started_at) : "Unknown time"}</small><b aria-hidden="true">⌄</b></div>
        </summary>
        <div className="automation-run-card-body">
          {run.error_message ? <div className="automation-run-error">{run.error_message}</div> : null}
          {trace ? <>
            <div className="automation-run-summary"><span>{counts.completed} completed</span><span>{counts.skipped} skipped</span><span>{counts.failed} failed</span><span>{nodeCount} total steps</span></div>
            <div className="automation-node-run-list">{(trace.node_runs ?? []).map((node, index) => {
              const expandable = nodeHasDetails(node);
              const headline = resultText(node.result) || node.summary || node.error || node.skip_reason || "Step completed";
              if (!expandable) return <div className={`automation-node-run ${node.status ?? "unknown"}`} key={`${run.id}-${node.node_id ?? index}`}>
                <span className="automation-node-run-index">{index + 1}</span>
                <div><strong>{node.label || `Step ${index + 1}`}</strong><small>{headline}</small></div>
                <em>{node.status || "unknown"}{typeof node.duration_ms === "number" ? ` · ${node.duration_ms}ms` : ""}</em>
              </div>;
              return <details className={`automation-node-run automation-node-run-expandable ${node.status ?? "unknown"}`} key={`${run.id}-${node.node_id ?? index}`}>
                <summary className="automation-node-run-summary">
                  <span className="automation-node-run-index">{index + 1}</span>
                  <span className="automation-node-run-copy"><strong>{node.label || `Step ${index + 1}`}</strong><small>{headline}</small></span>
                  <em>{node.status || "unknown"}{typeof node.duration_ms === "number" ? ` · ${node.duration_ms}ms` : ""}</em>
                  <span className="automation-node-run-chevron" aria-hidden="true">⌄</span>
                </summary>
                <NodeResultDetails node={node} />
              </details>;
            })}</div>
            <details className="automation-technical-disclosure"><summary>Advanced execution details</summary><small>Trigger source: {run.trigger_source} · Started: {run.started_at ? fmt(run.started_at) : "Unknown"}{run.finished_at ? ` · Finished: ${fmt(run.finished_at)}` : ""}</small></details>
          </> : <p className="automation-run-direct-summary">{String(run.output.summary || run.output.title || "Automation result preserved in run history.")}</p>}
        </div>
      </details>;
    })}
  </div>;
}

export function AutomationsPage() {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [builderOpen, setBuilderOpen] = useState(false);
  const [flowStudio, setFlowStudio] = useState<"new" | LifeOSAutomation | null>(null);
  const [activePanel, setActivePanel] = useState<{ id: number; view: "build" | "test" | "history" } | null>(null);
  const historyOpenId = activePanel?.view === "history" ? activePanel.id : null;
  const [previewingId, setPreviewingId] = useState<number | null>(null);
  const [previewResults, setPreviewResults] = useState<Record<number, { summary: string; output: Record<string, unknown> }>>({});
  const [runProposals, setRunProposals] = useState<Record<number, IntelligenceActionProposal>>({});
  const [proposalErrors, setProposalErrors] = useState<Record<number, string>>({});
  const [name, setName] = useState("My automation");
  const [triggerType, setTriggerType] = useState("schedule_daily");
  const [eventType, setEventType] = useState("task.overdue");
  const [hour, setHour] = useState(8);
  const [minute, setMinute] = useState(0);
  const [weekday, setWeekday] = useState(0);
  const [actionType, setActionType] = useState("today_briefing");
  const [projectId, setProjectId] = useState("");
  const browserTimezone = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC", []);
  const flowAutomationId = flowStudio && flowStudio !== "new" ? flowStudio.id : null;

  const registryQuery = useQuery({
    queryKey: ["automation-registry"],
    queryFn: () => apiGet<{ registry: AutomationRegistryData; runtime: { worker_enabled: boolean; poll_seconds: number; execution_available: boolean; workspace_mutation: boolean } }>("/api/v1/automations/registry"),
    retry: false,
  });
  const listQuery = useQuery({
    queryKey: ["lifeos-automations"],
    queryFn: () => apiGet<{ automations: LifeOSAutomation[]; count: number; preparation_mode: boolean; execution_available: boolean; worker_enabled: boolean }>("/api/v1/automations"),
    retry: false,
  });
  const historyQuery = useQuery({
    queryKey: ["automation-runs", historyOpenId],
    queryFn: () => apiGet<{ runs: AutomationRun[] }>(`/api/v1/automations/${historyOpenId}/runs?limit=15`),
    enabled: historyOpenId !== null,
    retry: false,
  });
  const latestRunQuery = useQuery({
    queryKey: ["automation-runs", flowAutomationId, "latest"],
    queryFn: () => apiGet<{ runs: AutomationRun[] }>(`/api/v1/automations/${flowAutomationId}/runs?limit=1`),
    enabled: flowAutomationId !== null,
    retry: false,
  });
  const projectsQuery = useQuery<ProjectListData>({ queryKey: ["projects", "automation-picker"], queryFn: fetchProjects, retry: false });
  const documentsQuery = useQuery({
    queryKey: ["documents", "automation-flow-picker"],
    queryFn: () => apiGet<{ items: DocumentSummary[] }>("/api/v1/documents"),
    enabled: Boolean(flowStudio),
    retry: false,
  });
  const modulesQuery = useQuery({
    queryKey: ["modules", "automation-flow-picker"],
    queryFn: () => apiGet<{ items: LearningModule[] }>("/api/v1/modules"),
    enabled: Boolean(flowStudio),
    retry: false,
  });
  const collectionsQuery = useQuery({
    queryKey: ["document-collections", "automation-flow-picker"],
    queryFn: () => apiGet<{ items: DocumentCollectionSummary[] }>("/api/v1/document-collections"),
    enabled: Boolean(flowStudio),
    retry: false,
  });

  async function refreshAutomationEvidence(id?: number) {
    await qc.invalidateQueries({ queryKey: ["lifeos-automations"] });
    if (id) {
      await qc.invalidateQueries({ queryKey: ["automation-runs", id] });
    }
  }

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiPost<{ automation: LifeOSAutomation }>("/api/v1/automations", payload),
    onSuccess: async (data) => {
      setError(null);
      setMessage(data.automation.execution.mode === "compiled_visual"
        ? `Created “${data.automation.name}”. You can test it now, then turn it on when you are happy with the result.`
        : `Created “${data.automation.name}”. You can test it now or turn it on.`);
      setBuilderOpen(false);
      setFlowStudio(null);
      await refreshAutomationEvidence();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "LifeOS could not create that automation."),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Record<string, unknown> }) => apiPatch<{ automation: LifeOSAutomation }>(`/api/v1/automations/${id}`, payload),
    onSuccess: async (data, variables) => {
      setError(null);
      if ("visual_graph" in variables.payload) {
        setMessage(data.automation.execution.mode === "compiled_visual"
          ? `Saved “${data.automation.name}”. LifeOS validated the flow and it is ready to run.`
          : `Saved “${data.automation.name}”.`);
        setFlowStudio(null);
      } else if ("enabled" in variables.payload) {
        setMessage(data.automation.enabled ? `Enabled “${data.automation.name}”.` : `Disabled “${data.automation.name}”.`);
      }
      await refreshAutomationEvidence(data.automation.id);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Automation could not be updated."),
  });

  const runMutation = useMutation({
    mutationFn: (id: number) => apiPost<{ execution: { output: Record<string, unknown>; notification_event_id: number | null } }>(`/api/v1/automations/${id}/run`, {}),
    onSuccess: async (data, id) => {
      setError(null);
      const output = data.execution.output;
      const summary = String(output.summary || output.title || "Automation completed from verified LifeOS state.");
      const proposal = recordValue(output.proposal);
      if (proposal && typeof proposal.id === "number") {
        setRunProposals((current) => ({ ...current, [id]: proposal as unknown as IntelligenceActionProposal }));
        setProposalErrors((current) => { const next = { ...current }; delete next[id]; return next; });
        setActivePanel({ id, view: "test" });
        setMessage("LifeOS finished the run and prepared an action for your approval.");
      } else {
        setMessage(data.execution.notification_event_id ? `${summary} A LifeOS notification was prepared.` : summary);
      }
      await refreshAutomationEvidence(id);
      await qc.invalidateQueries({ queryKey: ["lifeos-proactive-notifications"] });
    },
    onError: async (err, id) => {
      setError(err instanceof ApiError ? err.message : "Automation could not run. The failed run is preserved in history.");
      await refreshAutomationEvidence(id);
    },
  });

  const previewMutation = useMutation({
    mutationFn: (id: number) => apiPost<{ preview: { output: Record<string, unknown> } }>(`/api/v1/automations/${id}/preview`, {}),
    onMutate: (id) => {
      setError(null);
      setActivePanel({ id, view: "test" });
      setPreviewingId(id);
    },
    onSuccess: async (data, id) => {
      setError(null);
      const summary = String(data.preview.output.summary || data.preview.output.headline || data.preview.output.message || "Safe AI test completed from verified LifeOS state.");
      setPreviewResults((current) => ({ ...current, [id]: { summary, output: data.preview.output } }));
      await refreshAutomationEvidence(id);
    },
    onError: async (err, id) => {
      setError(err instanceof ApiError ? err.message : "Automation AI test failed. The failure is preserved in run history.");
      await refreshAutomationEvidence(id);
    },
    onSettled: () => setPreviewingId(null),
  });

  const proposalResolutionMutation = useMutation({
    mutationFn: ({ automationId, proposalId, mode }: { automationId: number; proposalId: number; mode: "confirm" | "dismiss" }) => apiPost<{ proposal: IntelligenceActionProposal }>(`/api/v1/intelligence/action-proposals/${proposalId}/${mode}`, {}),
    onMutate: ({ automationId }) => {
      setProposalErrors((current) => { const next = { ...current }; delete next[automationId]; return next; });
    },
    onSuccess: async (data, variables) => {
      setRunProposals((current) => ({ ...current, [variables.automationId]: data.proposal }));
      setMessage(data.proposal.status === "confirmed" ? "Approved action completed through I9." : data.proposal.status === "dismissed" ? "Proposal dismissed. Nothing was changed." : "Proposal updated.");
      await qc.invalidateQueries({ queryKey: ["projects"] });
      await qc.invalidateQueries({ queryKey: ["tasks"] });
      await qc.invalidateQueries({ queryKey: ["dashboard"] });
      await refreshAutomationEvidence(variables.automationId);
    },
    onError: (err, variables) => {
      setProposalErrors((current) => ({ ...current, [variables.automationId]: err instanceof ApiError ? err.message : "LifeOS could not update that proposal." }));
    },
  });

  const clearErrorMutation = useMutation({
    mutationFn: (id: number) => apiPost<{ automation: LifeOSAutomation; history_preserved: boolean }>(`/api/v1/automations/${id}/errors/clear`, {}),
    onSuccess: async (data) => {
      setError(null);
      setMessage(`Cleared the current error state for “${data.automation.name}”. Run history was preserved.`);
      await refreshAutomationEvidence(data.automation.id);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "LifeOS could not clear that error state."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/automations/${id}`),
    onSuccess: async () => { setMessage("Automation definition deleted."); setActivePanel(null); await refreshAutomationEvidence(); },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Automation could not be deleted."),
  });

  if (registryQuery.isPending || listQuery.isPending) return <PageState title="Loading Automations" text="Loading the LifeOS intelligence automation engine…" />;
  if (registryQuery.isError || listQuery.isError || !registryQuery.data || !listQuery.data) return <PageState title="Automations unavailable" text="LifeOS could not load the automation engine." error retry={() => { registryQuery.refetch(); listQuery.refetch(); }} />;

  const registry = registryQuery.data.registry;
  const runtime = registryQuery.data.runtime;
  const automations = listQuery.data.automations;

  function useTemplate(template: AutomationTemplate) {
    setMessage(null); setError(null);
    createMutation.mutate({
      name: template.name,
      description: template.description,
      enabled: false,
      trigger_type: template.trigger_type,
      trigger_config: template.trigger_config,
      action_type: template.action_type,
      action_config: template.action_config,
      timezone: browserTimezone,
    });
  }

  function useVisualTemplate(template: AutomationVisualTemplate) {
    setMessage(null); setError(null);
    createMutation.mutate({
      name: template.name,
      description: template.description,
      enabled: false,
      trigger_type: template.trigger_type,
      trigger_config: template.trigger_config,
      action_type: template.action_type,
      action_config: template.action_config,
      timezone: browserTimezone,
      visual_graph: template.visual_graph,
    });
  }

  function createCustom() {
    const triggerConfig = triggerType === "event"
      ? { event_type: eventType }
      : triggerType === "manual"
        ? {}
        : triggerType === "schedule_weekly"
          ? { weekday, hour, minute }
          : { hour, minute };
    const actionConfig = actionType === "project_review" ? { project_id: Number(projectId) } : {};
    setMessage(null); setError(null);
    createMutation.mutate({
      name,
      description: "Created in LifeOS Automations.",
      enabled: false,
      trigger_type: triggerType,
      trigger_config: triggerConfig,
      action_type: actionType,
      action_config: actionConfig,
      timezone: browserTimezone,
    });
  }

  function toggleAutomationPanel(id: number, view: "build" | "test" | "history") {
    setActivePanel((current) => current?.id === id && current.view === view ? null : { id, view });
  }

  return <section className="workspace-page automations-page">
    <PageHeader
      eyebrow="AI automations"
      title="Automations"
      description="Tell LifeOS when to think for you, what information to use, and what you want to happen with the result."
      actions={<div className="automation-header-actions"><button type="button" className="primary-button" onClick={() => { setBuilderOpen(false); setFlowStudio("new"); }}>✦ Build visual automation</button><button type="button" className="secondary-button" onClick={() => { setFlowStudio(null); setBuilderOpen((value) => !value); }}>{builderOpen ? "Close simple builder" : "+ Simple automation"}</button></div>}
    />

    <section className="automation-safety-banner">
      <div><span className={`automation-live-dot ${runtime.worker_enabled ? "enabled" : ""}`} /><div><strong>{runtime.worker_enabled ? "Background automations are on" : "Automations are ready to test"}</strong><p>{runtime.worker_enabled ? `LifeOS checks enabled automations about every ${runtime.poll_seconds} seconds and runs them when their time or event arrives.` : "Run now and Preview work immediately. Start the automation worker when you want scheduled and event automations to run in the background."}</p></div></div>
      <div className="automation-safety-pills"><span>Approved LifeOS steps only</span><span>Run history included</span><span>No direct database writes</span><span>Important changes ask first</span></div>
    </section>

    <section className="automation-explainer automation-explainer-compact panel-card">
      <div className="automation-explainer-copy">
        <span className="panel-kicker">How it works</span>
        <h2>When → Look at → Ask LifeOS to → Then</h2>
        <p>That is the whole automation. LifeOS only uses AI for reasoning; schedules, access, notifications, and approval stay controlled by normal application code.</p>
      </div>
      <details className="automation-explainer-details">
        <summary>See a quick example</summary>
        <div className="automation-explainer-example"><span>Example</span><strong>Every Sunday → E-commerce project → find important risks → only continue if attention is needed → notify me.</strong></div>
      </details>
    </section>

    {message ? <div className="form-alert success">{message}</div> : null}
    {error ? <div className="form-alert warning">{error}</div> : null}

    {flowStudio ? <VisualAutomationFlowBuilder
      key={flowStudio === "new" ? "new" : `automation-${flowStudio.id}`}
      registry={registry}
      projects={projectsQuery.data?.items ?? []}
      documents={documentsQuery.data?.items ?? []}
      modules={modulesQuery.data?.items ?? []}
      collections={collectionsQuery.data?.items ?? []}
      automation={flowStudio === "new" ? null : flowStudio}
      latestRun={flowStudio === "new" ? null : latestRunQuery.data?.runs?.[0] ?? null}
      timezone={browserTimezone}
      busy={createMutation.isPending || updateMutation.isPending}
      onCancel={() => setFlowStudio(null)}
      onSave={(payload) => {
        setMessage(null); setError(null);
        if (flowStudio === "new") createMutation.mutate(payload);
        else updateMutation.mutate({ id: flowStudio.id, payload });
      }}
    /> : null}

    {builderOpen ? <section className="panel-card automation-builder-card">
      <div className="section-heading"><div><span className="panel-kicker">Simple automation</span><h2>Create a one-step automation</h2><p>Choose when it should run and one LifeOS intelligence action. Use the visual builder when you want several steps.</p></div></div>
      <div className="automation-builder-grid">
        <label className="field-label">Name<input value={name} maxLength={160} onChange={(event) => setName(event.target.value)} /></label>
        <label className="field-label">When should it run?<select value={triggerType} onChange={(event) => setTriggerType(event.target.value)}>{registry.triggers.map((item) => <option value={item.type} key={item.type}>{item.label}</option>)}</select></label>
        {triggerType === "event" ? <label className="field-label">When this happens<select value={eventType} onChange={(event) => setEventType(event.target.value)}>{registry.event_types.map((item) => <option value={item} key={item}>{item.replace(/\./g, " · ")}</option>)}</select></label> : triggerType === "manual" ? <div className="visual-flow-locked-field"><span>When</span><strong>Only when you click Run now</strong><small>This one will not start automatically.</small></div> : <>
          {triggerType === "schedule_weekly" ? <label className="field-label">Weekday<select value={weekday} onChange={(event) => setWeekday(Number(event.target.value))}>{["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map((item, index) => <option value={index} key={item}>{item}</option>)}</select></label> : null}
          <label className="field-label">Hour<input type="number" min={0} max={23} value={hour} onChange={(event) => setHour(Number(event.target.value))} /></label>
          <label className="field-label">Minute<input type="number" min={0} max={59} value={minute} onChange={(event) => setMinute(Number(event.target.value))} /></label>
        </>}
        <label className="field-label">What should LifeOS do?<select value={actionType} onChange={(event) => setActionType(event.target.value)}>{registry.actions.filter((item) => !item.visual_only).map((item) => <option value={item.type} key={item.type}>{item.label}</option>)}</select></label>
        {actionType === "project_review" ? <label className="field-label">Project<select value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">Choose project</option>{(projectsQuery.data?.items ?? []).map((project) => <option value={project.id} key={project.id}>{project.title}</option>)}</select></label> : null}
        <label className="field-label">Timezone<input value={browserTimezone} readOnly /></label>
      </div>
      <div className="automation-builder-actions"><button type="button" className="secondary-button" onClick={() => setBuilderOpen(false)}>Cancel</button><button type="button" className="primary-button" disabled={createMutation.isPending || !name.trim() || (actionType === "project_review" && !projectId)} onClick={createCustom}>{createMutation.isPending ? "Creating…" : "Create automation"}</button></div>
    </section> : null}

    <section className="automation-template-section">
      <div className="section-heading"><div><span className="panel-kicker">Start here</span><h2>Ready-made automation recipes</h2><p>Pick one that sounds like what you want. You can open it afterward and change any step.</p></div></div>
      <div className="automation-template-grid">{(registry.visual_templates ?? []).map((template) => <VisualTemplateCard key={template.key} template={template} busy={createMutation.isPending} create={useVisualTemplate} />)}</div>
    </section>

    <details className="automation-simple-starters panel-card">
      <summary><div><span className="panel-kicker">Simple starters</span><strong>Need only one AI step?</strong><small>Open the one-step automation templates.</small></div><span aria-hidden="true">⌄</span></summary>
      <div className="automation-template-grid">{registry.templates.map((template) => <TemplateCard key={template.key} template={template} busy={createMutation.isPending} create={useTemplate} />)}</div>
    </details>

    <section className="panel-card automation-library-card">
      <div className="section-heading"><div><span className="panel-kicker">Automation library</span><h2>Your automations</h2><p>{automations.length} of {registry.limits.max_automations_per_user} available slots used.</p></div></div>
      {automations.length ? <div className="automation-list">{automations.map((item) => {
        const compiledSteps = item.compiled_plan?.steps ?? [];
        const isCompiledVisual = item.execution.mode === "compiled_visual";
        const flowLabels = compiledSteps.length ? compiledSteps.map(friendlyFlowStep) : [triggerLabel(item), actionLabel(registry, item.action.type)];
        const nextLabel = item.execution.background_available ? fmt(item.next_run_at) : "Manual only";
        const panelView = activePanel?.id === item.id ? activePanel.view : null;
        const buildOpen = panelView === "build";
        const testOpen = panelView === "test";
        const historyOpen = panelView === "history";
        const previewResult = previewResults[item.id];
        const previewTrace = previewResult ? visualTraceFromOutput(previewResult.output, "preview") : null;
        const previewCounts = traceCounts(previewTrace);
        const previewNodes = previewTrace?.node_runs ?? [];
        const previewAiNode = [...previewNodes].reverse().find((node) => node.capability?.startsWith("intelligence.") && Boolean(resultText(node.result)));
        const previewProposalNode = [...previewNodes].reverse().find((node) => node.capability?.startsWith("proposal.") && Boolean(node.result));
        const previewStoppedNode = [...previewNodes].reverse().find((node) => node.capability?.startsWith("condition.") && node.result?.condition_passed === false);
        const liveProposal = runProposals[item.id];
        const proposalBusy = proposalResolutionMutation.isPending && proposalResolutionMutation.variables?.automationId === item.id;
        const runningThis = runMutation.isPending && runMutation.variables === item.id;
        const previewingThis = previewingId === item.id;
        const sentence = automationSentence(item, registry);
        return <article className={`automation-row automation-product-card ${item.status === "error" ? "has-error" : ""}`} key={item.id}>
          <div className="automation-row-main automation-product-head">
            <div className="automation-row-title"><span className={`automation-status-dot ${item.enabled ? "enabled" : ""}`} /><div><strong>{item.name}</strong><small>{item.description || (isCompiledVisual ? "Visual LifeOS automation" : "Simple LifeOS automation")}</small></div></div>
            <div className="automation-product-status"><span className={`automation-current-status ${item.status}`}>{item.status}</span><span className={`automation-enabled-pill ${item.enabled ? "enabled" : ""}`}>{item.enabled ? "On" : item.execution.background_available ? "Off" : "Manual"}</span></div>
          </div>

          <div className="automation-human-summary"><span>What it does</span><strong>{sentence}</strong></div>

          <div className="automation-row-meta automation-product-meta"><span>Next · {nextLabel}</span><span>Last run · {item.last_run_at ? fmt(item.last_run_at) : "Never"}</span><span>Timezone · {item.timezone}</span>{compiledSteps.some((step) => step.category === "proposal") ? <span className="automation-ask-first-meta">Changes require your approval</span> : null}</div>

          <div className="automation-product-toolbar">
            <div className="automation-product-primary-actions">
              <button type="button" className="secondary-button flow-open-button" onClick={() => { setBuilderOpen(false); setFlowStudio(item); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Edit</button>
              <button type="button" className="primary-button" title="Run this automation now" disabled={runMutation.isPending || !item.execution.run_now_available} onClick={() => runMutation.mutate(item.id)}>{runningThis ? "Running…" : "Run now"}</button>
              <button type="button" className="secondary-button" title={!item.execution.background_available ? "Manual-trigger flows only run when you click Run now" : undefined} disabled={updateMutation.isPending || (!item.enabled && !item.execution.background_available)} onClick={() => updateMutation.mutate({ id: item.id, payload: { enabled: !item.enabled } })}>{item.enabled ? "Turn off" : item.execution.background_available ? "Turn on" : "Manual only"}</button>
            </div>
            <details className="automation-more-menu">
              <summary aria-label={`More options for ${item.name}`}>•••</summary>
              <div>
                <span className="automation-more-caption">{isCompiledVisual ? `Visual flow · ${compiledSteps.length} steps` : "Simple automation"}</span>
                {item.status === "error" ? <button type="button" className="secondary-button warning-soft" disabled={clearErrorMutation.isPending} onClick={() => clearErrorMutation.mutate(item.id)}>Clear current error</button> : null}
                <button type="button" className="secondary-button danger-soft" disabled={deleteMutation.isPending} onClick={() => { if (window.confirm(`Delete automation “${item.name}”?`)) deleteMutation.mutate(item.id); }}>Delete automation</button>
              </div>
            </details>
          </div>

          <div className="automation-mode-tabs" role="tablist" aria-label={`${item.name} views`}>
            <button type="button" role="tab" aria-selected={buildOpen} className={buildOpen ? "active" : ""} onClick={() => toggleAutomationPanel(item.id, "build")}>Build</button>
            <button type="button" role="tab" aria-selected={testOpen} className={testOpen ? "active" : ""} disabled={!item.execution.preview_available} onClick={() => toggleAutomationPanel(item.id, "test")}>Test</button>
            <button type="button" role="tab" aria-selected={historyOpen} className={historyOpen ? "active" : ""} onClick={() => toggleAutomationPanel(item.id, "history")}>History</button>
          </div>

          {buildOpen ? <section className="automation-mode-panel automation-build-panel" role="tabpanel">
            <div className="automation-mode-panel-head"><div><span className="panel-kicker">Build</span><strong>Your automation in order</strong><small>Edit the flow only when you want to change these steps.</small></div><button type="button" className="secondary-button" onClick={() => { setBuilderOpen(false); setFlowStudio(item); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Open builder</button></div>
            <div className="automation-flow automation-flow-compiled">{flowLabels.map((label, index) => <span className="automation-flow-step" key={`${item.id}-build-${index}-${label}`}>{index > 0 ? <b>→</b> : null}<em>{label}</em></span>)}</div>
            <details className="automation-technical-disclosure"><summary>Advanced details</summary><small>{isCompiledVisual ? `Backend-validated compiled flow · ${compiledSteps.length} steps · plan ${item.compiled_plan.plan_id}` : "Direct I17 automation"} · Important workspace changes still pass through {item.safety.confirmation_boundary || "I9 confirmation"}.</small></details>
          </section> : null}

          {testOpen ? <section className="automation-mode-panel automation-test-panel" role="tabpanel">
            <div className="automation-mode-panel-head"><div><span className="panel-kicker">Test</span><strong>See the result without changing your workspace</strong><small>The flow below is already backend-validated. Running the safe test can reason with AI, but approval steps are only simulated.</small></div><span className="automation-preview-safe">Read-only test</span></div>
            <div className="automation-preview-flow">{flowLabels.map((label, index) => <span key={`preview-${item.id}-${index}-${label}`}>{index > 0 ? <b>→</b> : null}<em>{label}</em></span>)}</div>
            <div className="automation-preview-actions">
              <div><strong>{previewResult ? "Test again with current LifeOS data" : "Ready to test the real output"}</strong><small>Common project risk questions use fast verified intelligence. Open-ended questions may call the AI provider and take longer.</small></div>
              <button type="button" className="primary-button" disabled={previewingThis || !item.execution.preview_available} onClick={() => previewMutation.mutate(item.id)}>{previewingThis ? "LifeOS is thinking…" : previewResult ? "Test again" : "Test AI safely"}</button>
            </div>
            {previewingThis ? <div className="automation-preview-progress"><span className="automation-preview-spinner" aria-hidden="true" /><div><strong>LifeOS is reasoning…</strong><small>This test cannot create tasks, save notes, or change your workspace.</small></div></div> : null}
            {previewResult && !previewingThis ? <div className="automation-preview-result automation-preview-result-clean">
              {previewAiNode ? <PreviewInsight node={previewAiNode} /> : <div className="automation-preview-result-head"><span className="panel-kicker">LifeOS result</span><strong>{previewResult.summary}</strong></div>}
              {previewStoppedNode ? <div className="automation-condition-stopped"><strong>Flow stopped safely</strong><span>The condition was not met, so later notification or approval steps were skipped.</span></div> : null}
              {liveProposal ? <LiveApproval proposal={liveProposal} busy={proposalBusy} error={proposalErrors[item.id]} onDismiss={() => proposalResolutionMutation.mutate({ automationId: item.id, proposalId: liveProposal.id, mode: "dismiss" })} onConfirm={() => proposalResolutionMutation.mutate({ automationId: item.id, proposalId: liveProposal.id, mode: "confirm" })} /> : previewProposalNode ? <PreviewApproval node={previewProposalNode} /> : null}
              <details className="automation-preview-technical"><summary>View technical execution · {previewCounts.completed} completed · {previewCounts.skipped} skipped · {previewCounts.failed} failed</summary>
                {previewTrace?.node_runs?.length ? <div className="automation-preview-node-list">{previewTrace.node_runs.map((node, index) => <span className={node.status ?? "unknown"} key={`preview-node-${item.id}-${node.node_id ?? index}`}><b>{index + 1}</b><em>{node.label || `Step ${index + 1}`}</em><small>{node.status || "unknown"}</small></span>)}</div> : <small>No technical trace was returned.</small>}
              </details>
            </div> : null}
            {liveProposal && !previewResult && !previewingThis ? <LiveApproval proposal={liveProposal} busy={proposalBusy} error={proposalErrors[item.id]} onDismiss={() => proposalResolutionMutation.mutate({ automationId: item.id, proposalId: liveProposal.id, mode: "dismiss" })} onConfirm={() => proposalResolutionMutation.mutate({ automationId: item.id, proposalId: liveProposal.id, mode: "confirm" })} /> : null}
          </section> : null}

          {historyOpen ? <section className="automation-mode-panel automation-history-panel" role="tabpanel">
            <div className="automation-mode-panel-head"><div><span className="panel-kicker">History</span><strong>Past runs and tests</strong><small>Runs stay compact. Open one only when you need its answer, evidence, timing, or failure details.</small></div></div>
            <RunHistory runs={historyQuery.data?.runs ?? []} loading={historyQuery.isPending} />
          </section> : null}
        </article>;
      })}</div> : <div className="dashboard-empty-state compact-empty-state"><div className="empty-state-icon">↻</div><h3>No automations yet</h3><p>Choose a recipe, build your own visual automation, or create a simple one-step automation. LifeOS keeps run history so you can always see what happened.</p></div>}
    </section>
  </section>;
}
