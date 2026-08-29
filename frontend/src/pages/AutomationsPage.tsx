import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiDelete, apiGet, apiPatch, apiPost } from "../api/client";
import type {
  AutomationRegistryData,
  AutomationTemplate,
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
  if (item.trigger.type === "schedule_daily") {
    return `Daily · ${String(config.hour ?? 8).padStart(2, "0")}:${String(config.minute ?? 0).padStart(2, "0")}`;
  }
  if (item.trigger.type === "schedule_weekly") {
    const labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    return `${labels[Number(config.weekday ?? 0)] ?? "Weekly"} · ${String(config.hour ?? 8).padStart(2, "0")}:${String(config.minute ?? 0).padStart(2, "0")}`;
  }
  return String(config.event_type || "LifeOS event").replace(/\./g, " · ");
}

function actionLabel(registry: AutomationRegistryData, type: string) {
  return registry.actions.find((item) => item.type === type)?.label ?? type.replace(/_/g, " ");
}

function TemplateCard({ template, busy, create }: { template: AutomationTemplate; busy: boolean; create: (template: AutomationTemplate) => void }) {
  return <article className="automation-template-card">
    <div className="automation-template-icon">↻</div>
    <div><span className="panel-kicker">Starter automation</span><h3>{template.name}</h3><p>{template.description}</p></div>
    <button type="button" className="secondary-button" disabled={busy} onClick={() => create(template)}>Use template</button>
  </article>;
}

export function AutomationsPage() {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [builderOpen, setBuilderOpen] = useState(false);
  const [flowStudio, setFlowStudio] = useState<"new" | LifeOSAutomation | null>(null);
  const [name, setName] = useState("My automation");
  const [triggerType, setTriggerType] = useState("schedule_daily");
  const [eventType, setEventType] = useState("task.overdue");
  const [hour, setHour] = useState(8);
  const [minute, setMinute] = useState(0);
  const [weekday, setWeekday] = useState(0);
  const [actionType, setActionType] = useState("today_briefing");
  const [projectId, setProjectId] = useState("");
  const browserTimezone = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC", []);

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
  const projectsQuery = useQuery<ProjectListData>({ queryKey: ["projects", "automation-picker"], queryFn: fetchProjects, retry: false });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiPost<{ automation: LifeOSAutomation }>("/api/v1/automations", payload),
    onSuccess: async (data) => {
      setError(null);
      setMessage(`Created “${data.automation.name}”. Enable it for scheduled/event execution, or use Run now to test it immediately.`);
      setBuilderOpen(false);
      setFlowStudio(null);
      await qc.invalidateQueries({ queryKey: ["lifeos-automations"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "LifeOS could not create that automation."),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Record<string, unknown> }) => apiPatch<{ automation: LifeOSAutomation }>(`/api/v1/automations/${id}`, payload),
    onSuccess: async (data, variables) => {
      setError(null);
      if ("visual_graph" in variables.payload) {
        setMessage(`Saved visual flow “${data.automation.name}”. The I17 runtime remains the execution source.`);
        setFlowStudio(null);
      }
      await qc.invalidateQueries({ queryKey: ["lifeos-automations"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Automation could not be updated."),
  });

  const runMutation = useMutation({
    mutationFn: (id: number) => apiPost<{ execution: { output: Record<string, unknown>; notification_event_id: number | null } }>(`/api/v1/automations/${id}/run`, {}),
    onSuccess: async (data) => {
      setError(null);
      const output = data.execution.output;
      const summary = String(output.summary || output.title || "Automation completed from verified LifeOS state.");
      setMessage(data.execution.notification_event_id ? `${summary} A LifeOS notification was prepared.` : summary);
      await qc.invalidateQueries({ queryKey: ["lifeos-automations"] });
      await qc.invalidateQueries({ queryKey: ["lifeos-proactive-notifications"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Automation could not run."),
  });

  const previewMutation = useMutation({
    mutationFn: (id: number) => apiPost<{ preview: { output: Record<string, unknown> } }>(`/api/v1/automations/${id}/preview`, {}),
    onSuccess: (data) => {
      setError(null);
      const summary = String(data.preview.output.summary || data.preview.output.headline || data.preview.output.message || "Preview completed from verified LifeOS state.");
      setMessage(summary);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Automation preview failed."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/automations/${id}`),
    onSuccess: async () => { setMessage("Automation definition deleted."); await qc.invalidateQueries({ queryKey: ["lifeos-automations"] }); },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Automation could not be deleted."),
  });

  if (registryQuery.isPending || listQuery.isPending) return <PageState title="Loading Automations" text="Loading the I17 intelligence automation engine…" />;
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

  function createCustom() {
    const triggerConfig = triggerType === "event"
      ? { event_type: eventType }
      : triggerType === "schedule_weekly"
        ? { weekday, hour, minute }
        : { hour, minute };
    const actionConfig = actionType === "project_review" ? { project_id: Number(projectId) } : {};
    setMessage(null); setError(null);
    createMutation.mutate({
      name,
      description: "Created in LifeOS Automations V1.",
      enabled: false,
      trigger_type: triggerType,
      trigger_config: triggerConfig,
      action_type: actionType,
      action_config: actionConfig,
      timezone: browserTimezone,
    });
  }

  return <section className="workspace-page automations-page">
    <PageHeader
      eyebrow="I18 · Visual intelligence flows"
      title="Automations"
      description="Build LifeOS intelligence automations visually or use the quick builder. The canvas compiles to the same safe I17 runtime; workspace changes still require I9 confirmation."
      actions={<div className="automation-header-actions"><button type="button" className="primary-button" onClick={() => { setBuilderOpen(false); setFlowStudio("new"); }}>✦ Visual Flow</button><button type="button" className="secondary-button" onClick={() => { setFlowStudio(null); setBuilderOpen((value) => !value); }}>{builderOpen ? "Close quick builder" : "+ Quick automation"}</button></div>}
    />

    <section className="automation-safety-banner">
      <div><span className={`automation-live-dot ${runtime.worker_enabled ? "enabled" : ""}`} /><div><strong>{runtime.worker_enabled ? "Background automation enabled" : "Automation engine ready"}</strong><p>{runtime.worker_enabled ? `The automation worker is configured to check enabled rules about every ${runtime.poll_seconds} seconds.` : "Run now works immediately. Scheduled and event rules begin when the backend automation worker is enabled."}</p></div></div>
      <div className="automation-safety-pills"><span>Intelligence, not basic reminders</span><span>No direct workspace writes</span><span>I9 confirmation stays required</span></div>
    </section>

    {message ? <div className="form-alert success">{message}</div> : null}
    {error ? <div className="form-alert warning">{error}</div> : null}

    {flowStudio ? <VisualAutomationFlowBuilder
      key={flowStudio === "new" ? "new" : `automation-${flowStudio.id}`}
      registry={registry}
      projects={projectsQuery.data?.items ?? []}
      automation={flowStudio === "new" ? null : flowStudio}
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
      <div className="section-heading"><div><span className="panel-kicker">Quick builder</span><h2>Create without the canvas</h2><p>The same reviewed triggers and read-only intelligence actions are available here as a compact form.</p></div></div>
      <div className="automation-builder-grid">
        <label className="field-label">Name<input value={name} maxLength={160} onChange={(event) => setName(event.target.value)} /></label>
        <label className="field-label">Trigger<select value={triggerType} onChange={(event) => setTriggerType(event.target.value)}>{registry.triggers.map((item) => <option value={item.type} key={item.type}>{item.label}</option>)}</select></label>
        {triggerType === "event" ? <label className="field-label">LifeOS event<select value={eventType} onChange={(event) => setEventType(event.target.value)}>{registry.event_types.map((item) => <option value={item} key={item}>{item.replace(/\./g, " · ")}</option>)}</select></label> : <>
          {triggerType === "schedule_weekly" ? <label className="field-label">Weekday<select value={weekday} onChange={(event) => setWeekday(Number(event.target.value))}>{["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map((item, index) => <option value={index} key={item}>{item}</option>)}</select></label> : null}
          <label className="field-label">Hour<input type="number" min={0} max={23} value={hour} onChange={(event) => setHour(Number(event.target.value))} /></label>
          <label className="field-label">Minute<input type="number" min={0} max={59} value={minute} onChange={(event) => setMinute(Number(event.target.value))} /></label>
        </>}
        <label className="field-label">Action<select value={actionType} onChange={(event) => setActionType(event.target.value)}>{registry.actions.map((item) => <option value={item.type} key={item.type}>{item.label}</option>)}</select></label>
        {actionType === "project_review" ? <label className="field-label">Project<select value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">Choose project</option>{(projectsQuery.data?.items ?? []).map((project) => <option value={project.id} key={project.id}>{project.title}</option>)}</select></label> : null}
        <label className="field-label">Timezone<input value={browserTimezone} readOnly /></label>
      </div>
      <div className="automation-builder-actions"><button type="button" className="secondary-button" onClick={() => setBuilderOpen(false)}>Cancel</button><button type="button" className="primary-button" disabled={createMutation.isPending || !name.trim() || (actionType === "project_review" && !projectId)} onClick={createCustom}>{createMutation.isPending ? "Creating…" : "Create automation"}</button></div>
    </section> : null}

    <section className="automation-template-section">
      <div className="section-heading"><div><span className="panel-kicker">Useful first</span><h2>Intelligence automations</h2><p>These automate analysis LifeOS already performs: daily focus, weekly review, compound-risk detection, and document follow-up checks.</p></div></div>
      <div className="automation-template-grid">{registry.templates.map((template) => <TemplateCard key={template.key} template={template} busy={createMutation.isPending} create={useTemplate} />)}</div>
    </section>

    <section className="panel-card automation-library-card">
      <div className="section-heading"><div><span className="panel-kicker">Automation library</span><h2>Your automations</h2><p>{automations.length} of {registry.limits.max_automations_per_user} available slots used.</p></div></div>
      {automations.length ? <div className="automation-list">{automations.map((item) => <article className="automation-row" key={item.id}>
        <div className="automation-row-main"><div className="automation-row-title"><span className={`automation-status-dot ${item.enabled ? "enabled" : ""}`} /><div><strong>{item.name}</strong><small>{item.description || actionLabel(registry, item.action.type)}</small></div></div><div className="automation-flow"><span>{triggerLabel(item)}</span><b>→</b><span>{actionLabel(registry, item.action.type)}</span></div></div>
        <div className="automation-row-meta"><span>Timezone · {item.timezone}</span><span>Next · {fmt(item.next_run_at)}</span><span>Last · {item.last_run_at ? fmt(item.last_run_at) : "Never"}</span><span>Workspace mutation · Off</span></div>
        <div className="automation-row-actions"><button type="button" className="secondary-button flow-open-button" onClick={() => { setBuilderOpen(false); setFlowStudio(item); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Open flow</button><button type="button" className="primary-button" disabled={runMutation.isPending} onClick={() => runMutation.mutate(item.id)}>{runMutation.isPending ? "Running…" : "Run now"}</button><button type="button" className="secondary-button" disabled={previewMutation.isPending} onClick={() => previewMutation.mutate(item.id)}>Preview</button><button type="button" className="secondary-button" disabled={updateMutation.isPending} onClick={() => updateMutation.mutate({ id: item.id, payload: { enabled: !item.enabled } })}>{item.enabled ? "Disable" : "Enable rule"}</button><button type="button" className="secondary-button danger-soft" disabled={deleteMutation.isPending} onClick={() => { if (window.confirm(`Delete automation “${item.name}”?`)) deleteMutation.mutate(item.id); }}>Delete</button></div>
      </article>)}</div> : <div className="dashboard-empty-state compact-empty-state"><div className="empty-state-icon">↻</div><h3>No automations yet</h3><p>Choose a starter automation, open the Visual Flow Studio, or use the quick builder. Use Run now first, then enable it when you are happy with the result.</p></div>}
    </section>
  </section>;
}
