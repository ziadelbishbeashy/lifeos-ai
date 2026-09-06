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
  if (raw.includes("ask")) return "Ask LifeOS";
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

  if (ai.isPending) return <PageState title="Loading AI usage" text="Reading LifeOS token and provider-cost telemetry…" />;
  if (ai.isError || !ai.data) return <PageState title="AI usage unavailable" text="LifeOS could not load AI usage telemetry." error retry={() => ai.refetch()} />;

  const usage = ai.data;
  const u = usage.totals || {};

  return <section className="analytics-page">
    <header className="analytics-hero">
      <div>
        <span className="analytics-eyebrow">Analytics · Development</span>
        <h1>AI usage & cost</h1>
        <p>Track provider calls, token consumption and estimated AI cost while LifeOS is under development.</p>
      </div>
      <div className="analytics-header-actions">
        <a href="/analytics" className="analytics-action-button secondary">Back to Analytics</a>
      </div>
    </header>

    <div className="analytics-filter-bar">
      <div className="analytics-filter-copy"><strong>AI usage period</strong><span>Provider telemetry recorded by LifeOS</span></div>
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
      <div className="analytics-panel-heading"><div><span>Feature breakdown</span><h2>Where AI usage is going</h2></div><strong className="analytics-panel-total">${Number(u.known_cost_usd || 0).toFixed(4)}</strong></div>
      {usage.by_feature?.length ? <div className="analytics-table-wrap"><table className="analytics-project-table"><thead><tr><th>AI feature</th><th>Calls</th><th>Avg tokens</th><th>Avg thinking</th><th>Total tokens</th><th>Avg cost / call</th><th>Known cost</th></tr></thead><tbody>{usage.by_feature.slice(0, 20).map((x: any) => <tr key={x.feature}><td><strong>{friendly(x.feature)}</strong></td><td><strong>{x.calls ?? 0}</strong></td><td><strong>{Number(x.average_tokens_per_call || 0).toLocaleString()}</strong></td><td><strong>{Number(x.average_thinking_tokens_per_call || 0).toLocaleString()}</strong></td><td><strong>{Number(x.total_tokens || 0).toLocaleString()}</strong></td><td><strong>{x.average_known_cost_usd == null ? "—" : `$${Number(x.average_known_cost_usd).toFixed(4)}`}</strong></td><td><strong>${Number(x.known_cost_usd || 0).toFixed(4)}</strong></td></tr>)}</tbody></table></div> : <div className="analytics-empty">Use an AI feature to begin collecting exact provider usage.</div>}
    </section>

    <section className="analytics-panel">
      <div className="analytics-panel-heading"><div><span>Operation cost</span><h2>Recent user operations</h2></div><strong className="analytics-panel-total">{u.operations ?? 0} operations</strong></div>
      {usage.recent_operations?.length ? <div className="analytics-table-wrap"><table className="analytics-project-table"><thead><tr><th>Operation</th><th>Provider calls</th><th>Tokens</th><th>Thinking</th><th>Cost</th><th>Metering</th></tr></thead><tbody>{usage.recent_operations.slice(0, 20).map((x: any) => <tr key={x.request_id}><td><strong>{operationLabel(x.endpoint, x.features)}</strong></td><td><strong>{x.calls ?? 0}</strong></td><td><strong>{Number(x.total_tokens || 0).toLocaleString()}</strong></td><td><strong>{Number(x.thinking_tokens || 0).toLocaleString()}</strong></td><td><strong>${Number(x.known_cost_usd || 0).toFixed(4)}</strong></td><td><strong>{x.cost_complete ? "Complete" : "Partial"}</strong></td></tr>)}</tbody></table></div> : <div className="analytics-empty">No AI operations have been recorded in this period.</div>}
    </section>
  </section>;
}
