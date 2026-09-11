import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet } from "../api/client";
import { PageState } from "../components/NativeUi";

function usageDays(period: string) {
  if (period === "today") return 1;
  if (period === "week") return 7;
  if (period === "90d") return 90;
  return 30;
}

function Summary({ tone, label, value, detail }: { tone: string; label: string; value: string | number; detail: string }) {
  return <article className={`analytics-summary-card accent-${tone}`}><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

function friendly(value: unknown) {
  return String(value || "unknown").replace(/_/g, " ");
}

function operationLabel(endpoint: unknown, features: unknown) {
  const raw = String(endpoint || "").trim();
  const featureList = Array.isArray(features) ? features : [];
  if (raw.includes("detect_type")) return "Detect document type";
  if (raw.includes("analyze_route")) return "Analyse document";
  if (raw.includes("ask")) return "Ask V-SPACE";
  if (raw.includes("assessment") && raw.includes("import")) return "Import academic schedule";
  if (featureList.length) return featureList.map(friendly).join(" + ");
  return raw ? raw.split(".").pop() || raw : "Internal AI operation";
}

export function AnalyticsAiUsagePage() {
  const [period, setPeriod] = useState("month");
  const days = usageDays(period);
  const ai = useQuery({
    queryKey: ["ai-usage", days],
    queryFn: () => apiGet<any>(`/api/v1/ai-usage/summary?days=${days}`),
  });

  if (ai.isPending) return <PageState title="Loading AI usage" text="Reading V-SPACE token and provider-cost telemetry…" />;
  if (ai.isError || !ai.data) return <PageState title="AI usage unavailable" text="V-SPACE could not load AI usage telemetry." error retry={() => ai.refetch()} />;

  const usage = ai.data;
  const u = usage.totals || {};
  const langsmith = usage.langsmith || {};
  const modelRouter = usage.model_router || {};
  const langsmithLabel = langsmith.state === "enabled" ? "Configured" : langsmith.state === "needs_api_key" ? "Needs API key" : langsmith.state === "sdk_unavailable" ? "SDK unavailable" : "Disabled";

  return <section className="analytics-page">
    <header className="analytics-hero">
      <div>
        <span className="analytics-eyebrow">Analytics · Development</span>
        <h1>AI usage & cost</h1>
        <p>Track provider calls, token consumption and estimated AI cost while V-SPACE is under development.</p>
      </div>
      <div className="analytics-header-actions">
        <a href="/analytics" className="analytics-action-button secondary">Back to Analytics</a>
      </div>
    </header>

    <div className="analytics-filter-bar">
      <div className="analytics-filter-copy"><strong>AI usage period</strong><span>Provider telemetry recorded by V-SPACE</span></div>
      <label><span>Range</span><select value={period} onChange={e => setPeriod(e.target.value)}><option value="today">Today</option><option value="week">This week</option><option value="month">This month</option><option value="30d">Last 30 days</option><option value="90d">Last 90 days</option></select></label>
    </div>

    <section className="analytics-summary-grid">
      <Summary tone="blue" label="AI calls" value={u.calls ?? 0} detail={`${u.successful_calls ?? 0} successful`} />
      <Summary tone="purple" label="AI operations" value={u.operations ?? 0} detail={`${u.operations_with_complete_cost ?? 0} fully metered`} />
      <Summary tone="purple" label="Total tokens" value={Number(u.total_tokens ?? 0).toLocaleString()} detail={`${Number(u.input_tokens ?? 0).toLocaleString()} input`} />
      <Summary tone="yellow" label="Thinking tokens" value={Number(u.thinking_tokens ?? 0).toLocaleString()} detail="Billed as model output" />
      <Summary tone="cyan" label="Cached input" value={Number(u.cached_input_tokens ?? 0).toLocaleString()} detail="Reduced input cost when supported" />
      <Summary tone="green" label="Known provider cost" value={`$${Number(u.known_cost_usd || 0).toFixed(4)}`} detail={`${u.calls_with_known_cost ?? 0} metered calls`} />
      <Summary tone="blue" label="Average operation" value={u.average_complete_operation_cost_usd == null ? "—" : `$${Number(u.average_complete_operation_cost_usd).toFixed(4)}`} detail="Across fully metered user operations" />
    </section>

    <section className="analytics-panel">
      <div className="analytics-panel-heading"><div><span>LangSmith</span><h2>Tracing status</h2></div><strong className="analytics-panel-total">{langsmithLabel}</strong></div>
      <div className="analytics-table-wrap"><table className="analytics-project-table"><thead><tr><th>Project</th><th>Sampling</th><th>Privacy</th><th>SDK</th></tr></thead><tbody><tr><td><strong>{langsmith.project || "lifeos-development"}</strong></td><td><strong>{Math.round(Number(langsmith.sampling_rate ?? 1) * 100)}%</strong></td><td><strong>{langsmith.raw_content_logged ? "Content logging enabled" : "Metadata only"}</strong></td><td><strong>{langsmith.sdk_available ? "Available" : "Unavailable"}</strong></td></tr></tbody></table></div>
      {langsmith.state === "needs_api_key" ? <div className="analytics-empty">Set LANGSMITH_API_KEY in backend/.env to start tracing.</div> : null}
    </section>

    <section className="analytics-panel">
      <div className="analytics-panel-heading"><div><span>Model router</span><h2>AI model tiers</h2></div><strong className="analytics-panel-total">{modelRouter.enabled ? "Enabled" : "Disabled"}</strong></div>
      {modelRouter.tiers?.length ? <div className="analytics-table-wrap"><table className="analytics-project-table"><thead><tr><th>Tier</th><th>Provider</th><th>Selected model</th><th>Configuration</th></tr></thead><tbody>{modelRouter.tiers.map((x: any) => <tr key={x.tier}><td><strong>{String(x.tier || "normal").toUpperCase()}</strong></td><td><strong>{modelRouter.provider || "—"}</strong></td><td><strong>{x.model || "—"}</strong></td><td><strong>{x.source === "requested_model" ? "Inherited" : x.source === "disabled" ? "Routing disabled" : "Tier override"}</strong></td></tr>)}</tbody></table></div> : <div className="analytics-empty">Model routing configuration is unavailable.</div>}
      <div className="analytics-empty">Unknown/new AI features default to NORMAL. Routing is deterministic and does not make an extra AI call.</div>
    </section>

    <section className="analytics-panel">
      <div className="analytics-panel-heading"><div><span>Feature breakdown</span><h2>Where AI usage is going</h2></div><strong className="analytics-panel-total">${Number(u.known_cost_usd || 0).toFixed(4)}</strong></div>
      {usage.by_feature?.length ? <div className="analytics-table-wrap"><table className="analytics-project-table"><thead><tr><th>AI feature</th><th>Model(s)</th><th>Calls</th><th>Avg tokens</th><th>Avg thinking</th><th>Total tokens</th><th>Avg cost / call</th><th>Known cost</th></tr></thead><tbody>{usage.by_feature.slice(0, 20).map((x: any) => <tr key={x.feature}><td><strong>{friendly(x.feature)}</strong></td><td><strong>{Array.isArray(x.models) && x.models.length ? x.models.join(", ") : "—"}</strong></td><td><strong>{x.calls ?? 0}</strong></td><td><strong>{Number(x.average_tokens_per_call || 0).toLocaleString()}</strong></td><td><strong>{Number(x.average_thinking_tokens_per_call || 0).toLocaleString()}</strong></td><td><strong>{Number(x.total_tokens || 0).toLocaleString()}</strong></td><td><strong>{x.average_known_cost_usd == null ? "—" : `$${Number(x.average_known_cost_usd).toFixed(4)}`}</strong></td><td><strong>${Number(x.known_cost_usd || 0).toFixed(4)}</strong></td></tr>)}</tbody></table></div> : <div className="analytics-empty">Use an AI feature to begin collecting exact provider usage.</div>}
    </section>

    <section className="analytics-panel">
      <div className="analytics-panel-heading"><div><span>Operation cost</span><h2>Recent user operations</h2></div><strong className="analytics-panel-total">{u.operations ?? 0} operations</strong></div>
      {usage.recent_operations?.length ? <div className="analytics-table-wrap"><table className="analytics-project-table"><thead><tr><th>Operation</th><th>Model(s)</th><th>Provider calls</th><th>Tokens</th><th>Thinking</th><th>Cost</th><th>Metering</th></tr></thead><tbody>{usage.recent_operations.slice(0, 20).map((x: any) => <tr key={x.request_id}><td><strong>{operationLabel(x.endpoint, x.features)}</strong></td><td><strong>{Array.isArray(x.models) && x.models.length ? x.models.join(", ") : "—"}</strong></td><td><strong>{x.calls ?? 0}</strong></td><td><strong>{Number(x.total_tokens || 0).toLocaleString()}</strong></td><td><strong>{Number(x.thinking_tokens || 0).toLocaleString()}</strong></td><td><strong>${Number(x.known_cost_usd || 0).toFixed(4)}</strong></td><td><strong>{x.cost_complete ? "Complete" : "Partial"}</strong></td></tr>)}</tbody></table></div> : <div className="analytics-empty">No AI operations have been recorded in this period.</div>}
    </section>
  </section>;
}
