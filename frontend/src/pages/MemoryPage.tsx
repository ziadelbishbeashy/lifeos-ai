import { useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiDelete, apiGet, apiPost } from "../api/client";
import { PageHeader, PageState } from "../components/NativeUi";

type MemoryItem = {
  id: number;
  type: "preference" | "current_focus" | "recent_project" | "dismissed_suggestion" | string;
  key: string;
  label: string;
  value: Record<string, unknown>;
  scope: { type: string; id: number | null } | null;
  source: { type: string; id: number | null; user_confirmed: boolean };
  created_at: string | null;
  updated_at: string | null;
  expires_at: string | null;
  status: string;
};

type MemoryData = {
  items: MemoryItem[];
  counts: Record<string, number>;
  policy: {
    structured_only: boolean;
    inspectable: boolean;
    deletable: boolean;
    stores_chat_transcripts: boolean;
    stores_raw_document_text: boolean;
    automatic_personal_inference: boolean;
  };
};

function memoryText(item: MemoryItem) {
  if (typeof item.value.text === "string") return item.value.text;
  if (typeof item.value.project_title === "string") return item.value.project_title;
  if (typeof item.value.event_type === "string") return String(item.value.event_type).replace(/_/g, " ").replace(/\./g, " · ");
  return "Structured workspace memory";
}

function sourceLabel(item: MemoryItem) {
  if (item.source.type === "user_confirmed") return "You saved this";
  if (item.source.type === "workspace_activity") return "Recent workspace activity";
  if (item.source.type === "notification_dismissal") return "Dismissed suggestion";
  return item.source.type.replace(/_/g, " ");
}

function formatDate(value: string | null) {
  if (!value) return null;
  const parsed = new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString();
}

export function MemoryPage() {
  const qc = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preferenceLabel, setPreferenceLabel] = useState("");
  const [preferenceValue, setPreferenceValue] = useState("");
  const [focusValue, setFocusValue] = useState("");

  const query = useQuery({
    queryKey: ["lifeos-memory"],
    queryFn: () => apiGet<{ memory: MemoryData }>("/api/v1/intelligence/memory"),
  });

  const refresh = useMutation({
    mutationFn: () => apiPost<{ memory: MemoryData }>("/api/v1/intelligence/memory/refresh", {}),
    onSuccess: async () => {
      setError(null);
      setMessage("Recent workspace memory refreshed.");
      await qc.invalidateQueries({ queryKey: ["lifeos-memory"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not refresh memory."),
  });

  const save = useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiPost("/api/v1/intelligence/memory", payload),
    onSuccess: async () => {
      setError(null);
      setMessage("Memory saved.");
      setPreferenceLabel("");
      setPreferenceValue("");
      setFocusValue("");
      await qc.invalidateQueries({ queryKey: ["lifeos-memory"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not save memory."),
  });

  const remove = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/intelligence/memory/${id}`),
    onSuccess: async () => {
      setError(null);
      setMessage("Memory deleted.");
      await qc.invalidateQueries({ queryKey: ["lifeos-memory"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not delete memory."),
  });

  const clear = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>("/api/v1/intelligence/memory/clear", {}),
    onSuccess: async (result) => {
      setError(null);
      setMessage(`Cleared ${result.deleted} memory item${result.deleted === 1 ? "" : "s"}.`);
      await qc.invalidateQueries({ queryKey: ["lifeos-memory"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not clear memory."),
  });

  const items = query.data?.memory.items ?? [];
  const groups = useMemo(() => ({
    controlled: items.filter((item) => item.type === "preference" || item.type === "current_focus"),
    recent: items.filter((item) => item.type === "recent_project"),
    dismissed: items.filter((item) => item.type === "dismissed_suggestion"),
  }), [items]);

  function savePreference(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    setError(null);
    save.mutate({ type: "preference", label: preferenceLabel, value: preferenceValue });
  }

  function saveFocus(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    setError(null);
    save.mutate({ type: "current_focus", label: "Current focus", value: focusValue });
  }

  if (query.isPending) return <PageState title="Opening Memory" text="Refreshing your controlled LifeOS memory…" />;
  if (query.isError || !query.data) return <PageState title="Memory unavailable" text="LifeOS could not load structured memory." error retry={() => query.refetch()} />;

  const policy = query.data.memory.policy;
  return <section className="workspace-page memory-page">
    <PageHeader
      eyebrow="I16 · Structured intelligence"
      title="Memory"
      description="Remember preferences naturally while talking to Ask LifeOS. This page is the control center where you inspect, correct, or delete what was saved."
      actions={<><button type="button" className="secondary-button" disabled={refresh.isPending} onClick={() => refresh.mutate()}>{refresh.isPending ? "Refreshing…" : "Refresh recent context"}</button><a className="secondary-button" href="/ask">Ask LifeOS</a></>}
    />

    {message ? <div className="form-alert success">{message}</div> : null}
    {error ? <div className="form-alert warning">{error}</div> : null}

    <div className="memory-policy-grid">
      <article><strong>Structured only</strong><span>{policy.structured_only ? "On" : "Off"}</span><p>Short typed values, not arbitrary conversation history.</p></article>
      <article><strong>Inspectable & deletable</strong><span>{policy.inspectable && policy.deletable ? "On" : "Off"}</span><p>You can see and remove every persisted memory row.</p></article>
      <article><strong>No hidden content</strong><span>{!policy.stores_chat_transcripts && !policy.stores_raw_document_text ? "On" : "Off"}</span><p>Raw chats and document text are never stored as I16 memory.</p></article>
    </div>

    <section className="memory-conversation-card">
      <div><span className="panel-kicker">Recommended</span><h2>Save memory while you talk</h2><p>Tell Ask LifeOS things like “I prefer short project reviews with risks first.” LifeOS will propose a memory and wait for your confirmation before saving it.</p></div>
      <a className="primary-button" href="/ask">Open Ask LifeOS</a>
    </section>

    <details className="memory-manual-details">
      <summary>Advanced · add memory manually</summary>
      <div className="memory-editor-grid">
        <form className="panel-card memory-editor-card" onSubmit={saveFocus}>
          <div className="section-heading"><div><span className="panel-kicker">Current focus</span><h2>What are you focused on?</h2><p>Saving a new focus replaces the previous one.</p></div></div>
          <label className="field-label">Focus<input value={focusValue} onChange={(event) => setFocusValue(event.target.value)} maxLength={500} placeholder="e.g. Finish LifeOS core intelligence before automations" /></label>
          <button className="primary-button" disabled={save.isPending || !focusValue.trim()}>Save current focus</button>
        </form>

        <form className="panel-card memory-editor-card" onSubmit={savePreference}>
          <div className="section-heading"><div><span className="panel-kicker">Preference</span><h2>Save a workspace preference</h2><p>Use this only when you want to enter structured memory directly.</p></div></div>
          <label className="field-label">Label<input value={preferenceLabel} onChange={(event) => setPreferenceLabel(event.target.value)} maxLength={180} placeholder="e.g. Project review style" /></label>
          <label className="field-label">Preference<input value={preferenceValue} onChange={(event) => setPreferenceValue(event.target.value)} maxLength={500} placeholder="e.g. Keep project reviews concise and prioritize blockers" /></label>
          <button className="primary-button" disabled={save.isPending || !preferenceLabel.trim() || !preferenceValue.trim()}>Save preference</button>
        </form>
      </div>
    </details>

    <section className="panel-card memory-library-card">
      <div className="section-heading"><div><span className="panel-kicker">Inspectable memory</span><h2>What LifeOS remembers</h2><p>{items.length} active memory item{items.length === 1 ? "" : "s"}. Derived memories expire automatically and are refreshed only when LifeOS checks recent context.</p></div>{items.length ? <button type="button" className="secondary-button danger-soft" disabled={clear.isPending} onClick={() => { if (window.confirm("Clear all LifeOS structured memory? This does not delete projects, tasks, notes, or documents.")) clear.mutate(); }}>Clear memory</button> : null}</div>

      {groups.controlled.length ? <div className="memory-group"><h3>You control</h3><div className="memory-card-grid">{groups.controlled.map((item) => <MemoryCard item={item} key={item.id} remove={() => remove.mutate(item.id)} busy={remove.isPending} />)}</div></div> : null}
      {groups.recent.length ? <div className="memory-group"><h3>Recently active projects</h3><div className="memory-card-grid">{groups.recent.map((item) => <MemoryCard item={item} key={item.id} remove={() => remove.mutate(item.id)} busy={remove.isPending} />)}</div></div> : null}
      {groups.dismissed.length ? <div className="memory-group"><h3>Dismissed suggestions</h3><div className="memory-card-grid">{groups.dismissed.map((item) => <MemoryCard item={item} key={item.id} remove={() => remove.mutate(item.id)} busy={remove.isPending} />)}</div></div> : null}
      {!items.length ? <div className="dashboard-empty-state compact-empty-state"><div className="empty-state-icon">M</div><h3>No structured memory yet</h3><p>Tell Ask LifeOS a preference or current focus, then confirm when it asks whether to remember it. Recent projects appear automatically when you use your workspace.</p></div> : null}
    </section>
  </section>;
}

function MemoryCard({ item, remove, busy }: { item: MemoryItem; remove: () => void; busy: boolean }) {
  const expiry = formatDate(item.expires_at);
  return <article className={`memory-card memory-${item.type}`}>
    <div className="memory-card-top"><span>{item.type.replace(/_/g, " ")}</span><button type="button" disabled={busy} onClick={remove} aria-label={`Delete ${item.label}`}>Delete</button></div>
    <strong>{item.label}</strong>
    <p>{memoryText(item)}</p>
    <div className="memory-card-meta"><span>{sourceLabel(item)}</span>{expiry ? <span>Expires {expiry}</span> : <span>Persistent until deleted</span>}</div>
  </article>;
}
