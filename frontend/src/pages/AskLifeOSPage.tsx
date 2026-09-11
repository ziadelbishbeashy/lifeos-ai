import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { ApiError, apiGet, apiPost } from "../api/client";
import { BrandMark, Icon } from "../components/VSpaceUi";
import { useSession } from "../auth/session";
import type { AgentActionSuggestion, AgentPlan, AgentRun } from "../api/types";

type AskScope = {
  type: string;
  id: number | null;
  label: string;
};

type AskModelTier = "cheap" | "normal" | "deep";

const askModelTierOptions: Array<{ value: AskModelTier; label: string; description: string }> = [
  { value: "cheap", label: "Fast", description: "Quick answers with lower AI cost" },
  { value: "normal", label: "Balanced", description: "Best for most V-SPACE questions" },
  { value: "deep", label: "Deep", description: "More reasoning for difficult requests" },
];

type AskContextOption = {
  type: "project" | "document" | "module" | "lecture" | "collection" | string;
  id: number;
  label: string;
  subtitle?: string | null;
  parent?: { type: string; id: number; label?: string | null } | null;
  project_id?: number | null;
};

type AskContextOptions = {
  groups: Record<string, AskContextOption[]>;
  counts: Record<string, number>;
  selection_mode: string;
  verified_ownership: boolean;
};

type GroundedAskResult = {
  kind: string;
  scope: AskContextOption;
  answer: string;
  sources: Array<Record<string, unknown>>;
  source_count: number;
  question_id?: number;
  reused_existing?: boolean;
  verified_grounding: boolean;
};

type ConversationMemorySuggestion = {
  type: "preference" | "current_focus" | string;
  label: string;
  value: string;
  project_id?: number | null;
  reason: string;
  requires_confirmation: boolean;
};

type AskCandidate = {
  type: string;
  id: number;
  label: string;
  confidence?: number;
};

type AskRoute = {
  intent: string;
  scope: AskScope | null;
  requires_clarification: boolean;
  candidates?: AskCandidate[];
};

type AskVerification = {
  status: "verified" | "rejected" | "trusted_fallback" | string;
  deterministic_checks_passed?: boolean;
  prose_check_performed?: boolean;
  checked_claims?: {
    factual: number;
    inference: number;
    recommendation: number;
  };
};

type AgentEvidence = {
  source_type: string;
  source_id?: number | null;
  label: string;
  field?: string;
  freshness?: string;
};

type ActionOption = {
  type: "create_task" | "create_note" | "refresh_document_analysis" | string;
  label: string;
  risk_level: string;
};

type AgentPriority = {
  project_id: number;
  project_title: string;
  category: string;
  severity: string;
  title: string;
  reason: string;
  recommended_action: string;
  evidence?: AgentEvidence[];
  actions?: ActionOption[];
  i9_authorization?: string;
};

type AskAgent = {
  kind: string;
  priorities?: AgentPriority[];
  reviewed_steps?: string[];
  context_limited?: boolean;
};

type ActionProposal = {
  id: number;
  action_type: string;
  status: "pending" | "executing" | "confirmed" | "dismissed" | "failed" | string;
  title: string;
  reason?: string | null;
  target: { type: string; id: number | null };
  project_id?: number | null;
  payload: Record<string, unknown>;
  evidence?: AgentEvidence[];
  risk_level: string;
  requires_confirmation: boolean;
  execution?: { resource_type: string; resource_id: number } | null;
  failure_message?: string | null;
};

type ActivityItem = {
  event_type: string;
  object_type: string;
  object_id?: number | null;
  project_id?: number | null;
  project_title?: string | null;
  title: string;
  summary?: string | null;
  occurred_at: string;
  source: string;
};

type ActivityResult = {
  window: { start_at: string; end_at: string; label: string };
  summary: string;
  items: ActivityItem[];
  total_items: number;
  context_limited: boolean;
};

type ContextResource = {
  type: string;
  id: number;
  label: string;
  url?: string | null;
  project_id?: number | null;
  project_title?: string | null;
  detail?: string | null;
};

type ContextConnection = {
  relation_type: string;
  relation_label: string;
  resource: ContextResource;
  reason?: string | null;
  provenance: { type: string; id?: number | null };
  evidence?: AgentEvidence[];
  persisted: boolean;
};

type ContextConnectionsResult = {
  resource: ContextResource | null;
  summary: string;
  connections: ContextConnection[];
  candidates: ContextResource[];
  counts: Record<string, number>;
  context_limited: boolean;
  verified_from_state: boolean;
  read_only: boolean;
};


type WorkspaceInsightItem = {
  type: string;
  title: string;
  detail: string;
  severity: string;
  status?: string | null;
  deadline?: string | null;
  project_id?: number | null;
  project_title?: string | null;
  module_id?: number | null;
  module_title?: string | null;
  object_id?: number | null;
  source?: { type: string; id?: number | null } | null;
  action_hint?: string | null;
};

type WorkspaceInsight = {
  kind: string;
  summary: string;
  items: WorkspaceInsightItem[];
  counts: Record<string, number>;
  context_limited: boolean;
  verified_from_state: boolean;
  read_only: boolean;
};

function groundedSourceLabel(source: Record<string, unknown>, index: number) {
  const filename = typeof source.filename === "string" ? source.filename : null;
  const page = typeof source.page === "number" || typeof source.page_number === "number"
    ? Number(source.page ?? source.page_number)
    : null;
  const section = typeof source.section === "string" ? source.section : null;
  const label = filename || (typeof source.label === "string" ? source.label : `Evidence ${index + 1}`);
  const detail = [page ? `page ${page}` : null, section].filter(Boolean).join(" · ");
  return detail ? `${label} · ${detail}` : label;
}

function formatActivityTime(value: string) {
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

type MemoryItem = {
  id: number;
  type: string;
  key: string;
  label: string;
  value: Record<string, unknown>;
  scope?: { type: string; id: number | null } | null;
  source: { type: string; id?: number | null; user_confirmed: boolean };
  expires_at?: string | null;
};

type MemoryResult = {
  summary: string;
  items: MemoryItem[];
  counts: Record<string, number>;
  policy: Record<string, boolean>;
  verified_from_state: boolean;
  user_controlled: boolean;
};

type AskWebSource = { id: string; title: string; url: string };
type AskDocumentSource = { id: string; document_id: number; filename: string; page?: number | null; section?: string | null };
type AskCapabilities = {
  request?: {
    task_type: string; complexity: string; knowledge_scope: string; needs_workspace: boolean;
    needs_rag: boolean; needs_web: boolean; needs_calculator: boolean; needs_code: boolean; action_mode: string;
  } | null;
  web?: { query: string; summary: string; sources: AskWebSource[]; source_count: number; read_only: boolean; provider_hosted_search: boolean } | null;
  calculation?: { expression: string; result: number; formatted_result: string; deterministic: boolean; code_execution: boolean } | null;
  documents?: { sources: AskDocumentSource[]; source_count: number; retrieval_mode: string; verified_grounding: boolean } | null;
  warnings?: string[];
  read_only: boolean;
};

type AskLifeOSResponse = {
  route: AskRoute;
  status: string;
  answer: string | null;
  response_mode: string;
  verification: AskVerification | null;
  attention_level: string | null;
  clarification: string | null;
  agent?: AskAgent | null;
  activity?: ActivityResult | null;
  insight?: WorkspaceInsight | null;
  connections?: ContextConnectionsResult | null;
  memory?: MemoryResult | null;
  grounded?: GroundedAskResult | null;
  memory_suggestion?: ConversationMemorySuggestion | null;
  goal_plan?: AgentPlan | null;
  capabilities?: AskCapabilities | null;
  reasoning_tier?: AskModelTier | null;
  read_only: boolean;
};

type ConversationItem = {
  id: number;
  role: "user" | "assistant";
  text: string;
  result?: AskLifeOSResponse;
  context?: AskContextOption | null;
};

type ClarificationContext = {
  intent: string;
};

const generalSuggestions = [
  "What should I do today?",
  "Which tasks are overdue?",
  "Help me get this project ready for deployment.",
  "What changed in V-SPACE this week?",
  "Which documents need review?",
  "Help me make meaningful progress this week.",
  "What should I study next?",
  "Review my project and tell me what needs attention",
];

function friendlyGoalTool(name: string) {
  const labels: Record<string, string> = {
    "workspace.get_home": "Check current priorities and deadlines",
    "workspace.get_recent_activity": "Check recent workspace changes",
    "workspace.get_portfolio_review": "Review project risks across V-SPACE",
    "project.get_summary": "Read the project state",
    "project.get_tasks": "Check tasks, blockers and deadlines",
    "project.review": "Review project priorities and risks",
    "project.get_documents": "Inspect related document intelligence",
    "project.get_recent_notes": "Read recent project notes and decisions",
    "knowledge.ask_context": "Use grounded knowledge from the selected context",
  };
  return labels[name] ?? name.replace(/[._]/g, " ");
}

function goalActionLabel(type: string) {
  if (type === "create_task") return "Create task";
  if (type === "create_note") return "Save note";
  if (type === "refresh_document_analysis") return "Refresh analysis";
  return type.replace(/_/g, " ");
}

function goalEvidenceGroups(evidence: AgentRun["output"]["evidence"] = []) {
  const groups = new Map<string, { label: string; items: NonNullable<AgentRun["output"]["evidence"]> }>();
  for (const entry of evidence || []) {
    const sourceRef = entry.source_refs?.find((ref) => typeof ref?.label === "string" || typeof ref?.filename === "string");
    const label = typeof sourceRef?.label === "string"
      ? sourceRef.label
      : typeof sourceRef?.filename === "string"
        ? sourceRef.filename
        : entry.project_title || "V-SPACE workspace";
    const current = groups.get(label) || { label, items: [] };
    current.items.push(entry);
    groups.set(label, current);
  }
  return Array.from(groups.values());
}

function answerSourceMaps(capabilities?: AskCapabilities | null) {
  const web = new Map((capabilities?.web?.sources || []).map((source) => [source.id, source]));
  const documents = new Map((capabilities?.documents?.sources || []).map((source) => [source.id, source]));
  return { web, documents };
}

function renderAnswerInline(text: string, capabilities?: AskCapabilities | null): ReactNode[] {
  const { web, documents } = answerSourceMaps(capabilities);
  const parts = text.split(/(\[(?:W|D)\d+\]|`[^`\n]+`|\*\*[^*\n]+\*\*|\\\([^\n]+?\\\))/g).filter(Boolean);
  return parts.map((part, index) => {
    const citation = /^\[((?:W|D)\d+)\]$/.exec(part);
    if (citation) {
      const id = citation[1];
      const webSource = web.get(id);
      if (webSource) return <a className="ask-lifeos-citation web" href={webSource.url} target="_blank" rel="noreferrer" key={`${id}-${index}`} title={webSource.title}>{id}</a>;
      const documentSource = documents.get(id);
      if (documentSource) return <a className="ask-lifeos-citation document" href={`/documents/${documentSource.document_id}`} key={`${id}-${index}`} title={documentSource.filename}>{id}</a>;
      return <span className="ask-lifeos-citation unresolved" key={`${id}-${index}`}>{id}</span>;
    }
    if (part.startsWith("`") && part.endsWith("`")) return <code className="ask-lifeos-inline-code" key={index}>{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("\\(") && part.endsWith("\\)")) return <span className="ask-lifeos-inline-equation" key={index}>{part.slice(2, -2)}</span>;
    return <span key={index}>{part}</span>;
  });
}

function AskCodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  }

  return <div className="ask-lifeos-code-block">
    <div className="ask-lifeos-code-head">
      <div className="ask-lifeos-code-meta"><span>{language || "code"}</span><em>generated · not executed</em></div>
      <button type="button" className="ask-lifeos-code-copy" onClick={copyCode} aria-label="Copy generated code">{copied ? "Copied" : "Copy"}</button>
    </div>
    <pre><code>{code}</code></pre>
  </div>;
}

function isTableDivider(line: string) {
  const cells = line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function tableCells(line: string) {
  return line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
}

function RichAskAnswer({ text, capabilities }: { text: string; capabilities?: AskCapabilities | null }) {
  const lines = String(text || "").replace(/\r\n?/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed) { index += 1; continue; }

    if (trimmed.startsWith("```")) {
      const language = trimmed.slice(3).trim();
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) { code.push(lines[index]); index += 1; }
      if (index < lines.length) index += 1;
      blocks.push(<AskCodeBlock language={language} code={code.join("\n")} key={`code-${blocks.length}`} />);
      continue;
    }

    if (trimmed.startsWith("$$") && trimmed.endsWith("$$") && trimmed.length > 4) {
      blocks.push(<div className="ask-lifeos-equation" key={`eq-${blocks.length}`}><span>{trimmed.slice(2, -2).trim()}</span></div>);
      index += 1;
      continue;
    }

    if (trimmed === "$$") {
      const equation: string[] = [];
      index += 1;
      while (index < lines.length && lines[index].trim() !== "$$") { equation.push(lines[index]); index += 1; }
      if (index < lines.length) index += 1;
      blocks.push(<div className="ask-lifeos-equation" key={`eq-${blocks.length}`}><span>{equation.join(" ").trim()}</span></div>);
      continue;
    }

    if (/^#{1,4}\s+/.test(trimmed)) {
      const level = (trimmed.match(/^#+/)?.[0].length || 2);
      const content = trimmed.replace(/^#{1,4}\s+/, "");
      const rendered = renderAnswerInline(content, capabilities);
      blocks.push(level <= 2 ? <h3 key={`h-${blocks.length}`}>{rendered}</h3> : <h4 key={`h-${blocks.length}`}>{rendered}</h4>);
      index += 1;
      continue;
    }

    if (index + 1 < lines.length && line.includes("|") && isTableDivider(lines[index + 1])) {
      const headers = tableCells(line);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) { rows.push(tableCells(lines[index])); index += 1; }
      blocks.push(<div className="ask-lifeos-table-wrap" key={`table-${blocks.length}`}><table><thead><tr>{headers.map((cell, cellIndex) => <th key={cellIndex}>{renderAnswerInline(cell, capabilities)}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{headers.map((_, cellIndex) => <td key={cellIndex}>{renderAnswerInline(row[cellIndex] || "", capabilities)}</td>)}</tr>)}</tbody></table></div>);
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) { items.push(lines[index].trim().replace(/^[-*]\s+/, "")); index += 1; }
      blocks.push(<ul className="ask-lifeos-rich-list unordered" key={`ul-${blocks.length}`}>{items.map((item, itemIndex) => <li key={itemIndex}>{renderAnswerInline(item, capabilities)}</li>)}</ul>);
      continue;
    }

    if (/^\d+[.)]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+[.)]\s+/.test(lines[index].trim())) { items.push(lines[index].trim().replace(/^\d+[.)]\s+/, "")); index += 1; }
      blocks.push(<ol className="ask-lifeos-rich-list ordered" key={`ol-${blocks.length}`}>{items.map((item, itemIndex) => <li key={itemIndex}>{renderAnswerInline(item, capabilities)}</li>)}</ol>);
      continue;
    }

    const paragraph: string[] = [trimmed];
    index += 1;
    while (index < lines.length) {
      const next = lines[index].trim();
      if (!next || next.startsWith("```") || next === "$$" || /^#{1,4}\s+/.test(next) || /^[-*]\s+/.test(next) || /^\d+[.)]\s+/.test(next)) break;
      if (index + 1 < lines.length && lines[index].includes("|") && isTableDivider(lines[index + 1])) break;
      paragraph.push(next); index += 1;
    }
    blocks.push(<p key={`p-${blocks.length}`}>{renderAnswerInline(paragraph.join(" "), capabilities)}</p>);
  }

  return <div className="ask-lifeos-rich-answer">{blocks}</div>;
}

function CapabilityEvidence({ capabilities }: { capabilities?: AskCapabilities | null }) {
  const webSources = capabilities?.web?.sources || [];
  const documentSources = capabilities?.documents?.sources || [];
  const calculation = capabilities?.calculation;
  const warnings = capabilities?.warnings || [];
  const sourceCount = webSources.length + documentSources.length;
  const [sourcesOpen, setSourcesOpen] = useState(sourceCount <= 3);
  if (!capabilities || (!sourceCount && !calculation && !warnings.length)) return null;
  return <section className="ask-lifeos-capability-evidence">
    {calculation ? <div className="ask-lifeos-calculation-card"><div><span>Deterministic calculation</span><small>Computed by V-SPACE code, not estimated by the model</small></div><strong>{calculation.formatted_result}</strong><code>{calculation.expression}</code></div> : null}
    {sourceCount ? <details className="ask-lifeos-evidence-panel" open={sourcesOpen} onToggle={(event) => setSourcesOpen(event.currentTarget.open)}>
      <summary>
        <div className="ask-lifeos-evidence-summary-copy">
          <span className="ask-lifeos-evidence-icon" aria-hidden="true">↗</span>
          <div><strong>Sources & evidence</strong><small>{sourceCount} {sourceCount === 1 ? "reference" : "references"} used in this answer</small></div>
        </div>
        <span className="ask-lifeos-evidence-toggle">{sourcesOpen ? "Hide" : "View"}</span>
      </summary>
      <div className="ask-lifeos-evidence-body">
        {webSources.length ? <div className="ask-lifeos-source-group"><div className="ask-lifeos-source-heading"><strong>Web sources</strong><span>Read-only research</span></div><div className="ask-lifeos-source-cards">{webSources.slice(0, 8).map((source) => <a href={source.url} target="_blank" rel="noreferrer" key={source.id}><span>{source.id}</span><strong>{source.title}</strong><small>{(() => { try { return new URL(source.url).hostname; } catch { return "Public web"; } })()}</small><em aria-hidden="true">↗</em></a>)}</div></div> : null}
        {documentSources.length ? <div className="ask-lifeos-source-group"><div className="ask-lifeos-source-heading"><strong>Document evidence</strong><span>Owned V-SPACE knowledge</span></div><div className="ask-lifeos-source-cards documents">{documentSources.slice(0, 8).map((source) => <a href={`/documents/${source.document_id}`} key={source.id}><span>{source.id}</span><strong>{source.filename}</strong><small>{[source.page ? `page ${source.page}` : null, source.section].filter(Boolean).join(" · ") || "Document Brain"}</small><em aria-hidden="true">→</em></a>)}</div></div> : null}
      </div>
    </details> : null}
    {warnings.length ? <details className="ask-lifeos-capability-warnings"><summary>Capability notes</summary>{warnings.map((warning, warningIndex) => <p key={warningIndex}>{warning}</p>)}</details> : null}
  </section>;
}

function TrustBadge({ result }: { result: AskLifeOSResponse }) {
  if (result.response_mode === "goal_plan") {
    return <span className="ask-lifeos-trust verified"><i />Safe plan · nothing run yet</span>;
  }
  if (result.response_mode === "grounded_rag_verified" && result.verification?.status === "verified") {
    return <span className="ask-lifeos-trust verified"><i />Grounded in selected context</span>;
  }
  if (result.response_mode === "memory_proposal") {
    return <span className="ask-lifeos-trust neutral"><i />Waiting for your confirmation</span>;
  }
  if (result.response_mode === "agent_verified" && result.verification?.status === "verified") {
    return <span className="ask-lifeos-trust verified"><i />Verified priority review</span>;
  }
  if (["ai_verified", "ai_verified_fast", "general_ai_verified", "general_ai_verified_fast", "deterministic_verified"].includes(result.response_mode) && result.verification?.status === "verified") {
    return <span className="ask-lifeos-trust verified"><i />Verified intelligence</span>;
  }
  if (result.response_mode === "deterministic_calculation" && result.verification?.status === "verified") {
    return <span className="ask-lifeos-trust verified"><i />Deterministic calculation</span>;
  }
  if (["capability_fallback", "reasoning_unavailable", "reasoning_rejected"].includes(result.response_mode)) {
    return <span className="ask-lifeos-trust fallback"><i />Safe capability boundary</span>;
  }
  if (result.response_mode === "deterministic_fallback") {
    return <span className="ask-lifeos-trust fallback"><i />Trusted state fallback</span>;
  }
  if (result.status === "clarification_required") {
    return <span className="ask-lifeos-trust neutral"><i />Needs clarification</span>;
  }
  return <span className="ask-lifeos-trust neutral"><i />Verified intelligence boundary</span>;
}

function responseSurfaceTone(result?: AskLifeOSResponse | null) {
  if (!result) return "tone-neutral";
  if (result.status === "clarification_required") return "tone-neutral";
  if (result.verification?.status === "verified") return "tone-verified";
  if (result.verification?.status === "trusted_fallback" || ["capability_fallback", "reasoning_unavailable", "reasoning_rejected", "deterministic_fallback"].includes(result.response_mode)) return "tone-fallback";
  return "tone-neutral";
}

function AskResponseCopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  async function copyAnswer() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return <button type="button" className={`ask-lifeos-response-copy ${copied ? "copied" : ""}`} onClick={copyAnswer} aria-label="Copy V-SPACE answer" title="Copy answer">
    <span className="ask-lifeos-response-copy-icon" aria-hidden="true">{copied ? "✓" : "⧉"}</span>
    <span>{copied ? "Copied" : "Copy"}</span>
  </button>;
}

function AssistantMessage({ item, onReply, onRemember }: { item: ConversationItem; onReply: (text: string) => void; onRemember: (suggestion: ConversationMemorySuggestion) => void }) {
  const result = item.result;
  const candidates = result?.status === "clarification_required" ? (result.route.candidates || []) : [];
  const priorities = result?.agent?.priorities || [];
  const activity = result?.activity;
  const insight = result?.insight;
  const connections = result?.connections;
  const memory = result?.memory;
  const grounded = result?.grounded;
  const memorySuggestion = result?.memory_suggestion;
  const goalPlan = result?.goal_plan || null;
  const [showAllPriorities, setShowAllPriorities] = useState(false);
  const [proposal, setProposal] = useState<ActionProposal | null>(null);
  const [proposalBusy, setProposalBusy] = useState(false);
  const [proposalError, setProposalError] = useState<string | null>(null);
  const [showMemorySuggestion, setShowMemorySuggestion] = useState(true);
  const [goalRun, setGoalRun] = useState<AgentRun | null>(null);
  const [goalRunBusy, setGoalRunBusy] = useState(false);
  const [goalRunError, setGoalRunError] = useState<string | null>(null);
  const [showGoalEvidence, setShowGoalEvidence] = useState(false);
  const [showGoalTechnical, setShowGoalTechnical] = useState(false);
  const [showPriorityEvidence, setShowPriorityEvidence] = useState(false);
  const topPriority = priorities[0] || null;
  const goalSummary = goalRun?.output.goal_summary || null;
  const goalEvidence = goalEvidenceGroups(goalRun?.output.evidence || []);

  async function createProposal(priority: AgentPriority, actionType: string) {
    if (proposalBusy || proposal?.status === "pending" || proposal?.status === "executing") return;
    setProposalBusy(true);
    setProposalError(null);
    try {
      const response = await apiPost<{ proposal: ActionProposal }>("/api/v1/intelligence/action-proposals", {
        action_type: actionType,
        priority,
      });
      setProposal(response.proposal);
    } catch (err) {
      setProposalError(err instanceof ApiError ? err.message : "V-SPACE could not prepare that action.");
    } finally {
      setProposalBusy(false);
    }
  }

  async function confirmProposal() {
    if (!proposal || proposalBusy || proposal.status !== "pending") return;
    setProposalBusy(true);
    setProposalError(null);
    try {
      const response = await apiPost<{ proposal: ActionProposal }>(`/api/v1/intelligence/action-proposals/${proposal.id}/confirm`, {});
      setProposal(response.proposal);
    } catch (err) {
      setProposalError(err instanceof ApiError ? err.message : "V-SPACE could not complete that action.");
    } finally {
      setProposalBusy(false);
    }
  }

  async function dismissProposal() {
    if (!proposal || proposalBusy || proposal.status !== "pending") return;
    setProposalBusy(true);
    setProposalError(null);
    try {
      const response = await apiPost<{ proposal: ActionProposal }>(`/api/v1/intelligence/action-proposals/${proposal.id}/dismiss`, {});
      setProposal(response.proposal);
    } catch (err) {
      setProposalError(err instanceof ApiError ? err.message : "V-SPACE could not dismiss that action.");
    } finally {
      setProposalBusy(false);
    }
  }

  async function startGoalReview() {
    if (!goalPlan || goalRunBusy) return;
    setGoalRunBusy(true);
    setGoalRunError(null);
    setGoalRun(null);
    setProposal(null);
    try {
      const selectedContext = goalPlan.scope.type === "workspace" || goalPlan.scope.id == null
        ? null
        : { type: goalPlan.scope.type, id: goalPlan.scope.id };
      const response = await apiPost<{ run: AgentRun }>("/api/v1/intelligence/goal-runs", {
        goal: goalPlan.goal,
        selected_context: selectedContext,
        model_tier: result?.reasoning_tier ?? null,
      });
      setGoalRun(response.run);
      if (response.run.status === "failed") {
        setGoalRunError(response.run.failure_message || "V-SPACE could not complete this goal review.");
      }
    } catch (err) {
      setGoalRunError(err instanceof ApiError ? err.message : "V-SPACE could not complete this goal review.");
    } finally {
      setGoalRunBusy(false);
    }
  }

  async function prepareGoalProposal(suggestion: AgentActionSuggestion, actionType: string) {
    if (!goalRun || proposalBusy) return;
    setProposalBusy(true);
    setProposalError(null);
    try {
      const response = await apiPost<{ proposal: ActionProposal }>(`/api/v1/intelligence/goal-runs/${goalRun.id}/proposals`, {
        suggestion_id: suggestion.id,
        action_type: actionType,
      });
      setProposal(response.proposal);
    } catch (err) {
      setProposalError(err instanceof ApiError ? err.message : "V-SPACE could not prepare that action.");
    } finally {
      setProposalBusy(false);
    }
  }

  return <div className="ask-lifeos-message assistant-message">
    <div className="ask-lifeos-avatar lifeos-avatar" aria-hidden="true"><BrandMark/></div>
    <div className="ask-lifeos-message-body">
      <div className="ask-lifeos-message-label">V-SPACE</div>
      <article className={`ask-lifeos-response-card ${responseSurfaceTone(result)}`}>
        <header className="ask-lifeos-response-head">
          <div className="ask-lifeos-response-status">
            <span className="ask-lifeos-response-spark" aria-hidden="true">✦</span>
            {result ? <TrustBadge result={result} /> : <span className="ask-lifeos-trust neutral"><i />V-SPACE response</span>}
          </div>
          <AskResponseCopyButton text={item.text} />
        </header>
        <div className="ask-lifeos-answer"><RichAskAnswer text={item.text} capabilities={result?.capabilities} /></div>
        <CapabilityEvidence capabilities={result?.capabilities} />
      </article>
      {result?.status === "clarification_required" ? <div className="ask-lifeos-clarification-actions">
        {candidates.map((candidate) => <button type="button" key={candidate.id} onClick={() => onReply(candidate.label)}>{candidate.label}</button>)}
        <button type="button" className="all-projects" onClick={() => onReply("all")}>All projects</button>
      </div> : null}
      {goalPlan ? <section className={`ask-lifeos-goal-review ${goalRun?.status === "succeeded" ? "completed" : ""}`}>
        <div className="ask-lifeos-goal-heading">
          <div><span>Goal review</span><strong>{goalPlan.scope.label}</strong></div>
          <span className="ask-lifeos-goal-safety">Read-only checks</span>
        </div>
        {!goalRun ? <div className="ask-lifeos-goal-plan">
          {goalPlan.steps.map((step, index) => <div className="ask-lifeos-goal-step state-ready" key={step.step_id}>
            <span className="ask-lifeos-goal-step-state">{index + 1}</span>
            <div><strong>{friendlyGoalTool(step.tool_name)}</strong><small>{step.purpose}</small></div>
          </div>)}
        </div> : null}
        {!goalRun ? <div className="ask-lifeos-goal-start">
          <p>V-SPACE has not run these checks yet. Starting the review can read only your owned workspace; any later change still needs I9 confirmation.</p>
          <button type="button" className="primary" disabled={goalRunBusy} onClick={() => void startGoalReview()}>{goalRunBusy ? "Reviewing…" : "Start review"}</button>
        </div> : null}
        {goalRunBusy ? <div className="ask-lifeos-goal-running"><span/><div><strong>Reviewing the goal with trusted V-SPACE context…</strong><small>Checking project state, tasks, priorities and relevant knowledge. No workspace changes can happen during this review.</small></div></div> : null}
        {goalRunError ? <div className="ask-lifeos-goal-retry"><div className="ask-lifeos-action-error standalone">{goalRunError}</div><button type="button" disabled={goalRunBusy} onClick={() => void startGoalReview()}>Try review again</button></div> : null}
        {goalRun?.status === "succeeded" ? <div className="ask-lifeos-goal-result">
          <div className="ask-lifeos-goal-executive-head">
            <div>
              <span className="ask-lifeos-goal-result-kicker">Goal assessment</span>
              <strong>{goalSummary?.headline || "V-SPACE completed the trusted checks for this goal."}</strong>
            </div>
            {goalSummary?.status_label ? <span className={`ask-lifeos-goal-status status-${goalSummary.status}`}>{goalSummary.status_label}</span> : null}
          </div>

          {goalSummary?.biggest_blocker ? <section className="ask-lifeos-goal-blocker">
            <span>Biggest blocker</span>
            <strong>{goalSummary.biggest_blocker.title}</strong>
            {goalSummary.biggest_blocker.why ? <p>{goalSummary.biggest_blocker.why}</p> : null}
          </section> : <div className="ask-lifeos-goal-answer">{goalRun.output.answer || "V-SPACE completed the review but did not produce a stronger conclusion."}</div>}

          {goalSummary?.other_risks?.length ? <section className="ask-lifeos-goal-other-risks">
            <strong>Other important risks</strong>
            <div>{goalSummary.other_risks.slice(0, 3).map((risk) => <article key={`${risk.evidence_id || risk.title}`}>
              <span className={`risk-${risk.severity || "medium"}`} aria-hidden="true" />
              <div><b>{risk.title}</b>{risk.why ? <p>{risk.why}</p> : null}</div>
            </article>)}</div>
          </section> : null}

          <section className="ask-lifeos-goal-conclusion">
            <details>
              <summary>V-SPACE conclusion</summary>
              <div className="ask-lifeos-goal-answer">{goalRun.output.answer || "V-SPACE completed the review but did not produce a stronger conclusion."}</div>
            </details>
          </section>

          {(goalSummary?.focus_steps?.length || goalRun.output.recommendations?.length) ? <div className="ask-lifeos-goal-recommendations">
            <strong>What I would do next</strong>
            <ol>{(goalSummary?.focus_steps?.length ? goalSummary.focus_steps : (goalRun.output.recommendations || []).map((entry) => entry.text)).slice(0, 3).map((entry, index) => <li key={`${entry}-${index}`}>{entry}</li>)}</ol>
          </div> : null}

          {goalRun.output.action_suggestions?.length ? <div className="ask-lifeos-goal-actions">
            <div><strong>Suggested actions</strong><span>V-SPACE will ask before changing anything.</span></div>
            {goalRun.output.action_suggestions.slice(0, 2).map((suggestion) => <article key={suggestion.id}>
              <div><strong>{suggestion.title}</strong><p>{suggestion.recommended_action || suggestion.reason}</p></div>
              <div className="ask-lifeos-goal-action-buttons">{suggestion.options.slice(0, 2).map((option) => <button type="button" key={option.type} disabled={proposalBusy || proposal?.status === "pending"} onClick={() => void prepareGoalProposal(suggestion, option.type)}>{goalActionLabel(option.type)}</button>)}</div>
            </article>)}
          </div> : null}

          {goalRun.output.evidence?.length ? <div className="ask-lifeos-goal-disclosure">
            <button type="button" onClick={() => setShowGoalEvidence((value) => !value)}>{showGoalEvidence ? "Hide evidence" : `View evidence · ${goalSummary?.source_count ?? goalEvidence.length} ${((goalSummary?.source_count ?? goalEvidence.length) === 1) ? "source" : "sources"} · ${goalSummary?.finding_count ?? goalRun.output.evidence.length} findings`}</button>
            {showGoalEvidence ? <div className="ask-lifeos-goal-evidence grouped">{goalEvidence.slice(0, 8).map((group) => <section key={group.label}>
              <div className="ask-lifeos-goal-evidence-source"><span>D</span><strong>{group.label}</strong><small>{group.items.length} {group.items.length === 1 ? "finding" : "findings"}</small></div>
              <div>{group.items.slice(0, 5).map((entry) => <article key={entry.id}><strong>{entry.label}</strong>{entry.detail ? <p>{entry.detail}</p> : null}</article>)}</div>
            </section>)}</div> : null}
          </div> : null}

          <div className="ask-lifeos-goal-disclosure technical">
            <button type="button" onClick={() => setShowGoalTechnical((value) => !value)}>{showGoalTechnical ? "Hide technical details" : "Advanced · review details"}</button>
            {showGoalTechnical ? <div className="ask-lifeos-goal-technical">
              <span>{goalRun.metrics.tool_calls} tool calls</span><span>{goalRun.metrics.provider_calls} AI calls</span><span>{goalRun.output.verification_status || "verified boundary"}</span>
              {goalRun.trace.map((step) => <div key={step.step_id}><strong>{friendlyGoalTool(step.tool_name)}</strong><span>{step.status} · {Math.round(step.duration_ms)} ms</span></div>)}
            </div> : null}
          </div>
        </div> : null}
      </section> : null}
      {priorities.length && topPriority ? <div className="ask-lifeos-priority-list compact">
        <article className={`ask-lifeos-priority-focus ask-lifeos-priority-${topPriority.severity}`}>
          <div className="ask-lifeos-priority-focus-head"><span>Top focus</span>{result?.route.scope?.type === "portfolio" ? <small>{topPriority.project_title}</small> : null}</div>
          <strong>{topPriority.title}</strong>
          <p>{topPriority.reason}</p>
          <div className="ask-lifeos-priority-next"><b>Next:</b> {topPriority.recommended_action}</div>
          {topPriority.actions?.length ? <div className="ask-lifeos-priority-actions consolidated">
            {topPriority.actions.slice(0, 2).map((action) => <button type="button" key={action.type} disabled={proposalBusy || proposal?.status === "pending" || proposal?.status === "executing"} onClick={() => void createProposal(topPriority, action.type)}>{action.label}</button>)}
          </div> : null}
        </article>

        {priorities.length > 1 ? <button type="button" className="ask-lifeos-priority-toggle" onClick={() => setShowAllPriorities((value) => !value)}>
          {showAllPriorities ? "Hide other findings" : `View ${priorities.length - 1} other ${priorities.length - 1 === 1 ? "finding" : "findings"}`}
        </button> : null}

        {showAllPriorities ? <div className="ask-lifeos-priority-secondary-list">{priorities.slice(1).map((priority, index) => <article key={`${priority.project_id}-${priority.category}-${index}`}>
          <span>{index + 2}</span>
          <div><strong>{priority.title}</strong><p>{priority.reason}</p>{result?.route.scope?.type === "portfolio" ? <small>{priority.project_title}</small> : null}</div>
        </article>)}</div> : null}

        {priorities.some((priority) => priority.evidence?.length) ? <div className="ask-lifeos-priority-evidence-toggle">
          <button type="button" onClick={() => setShowPriorityEvidence((value) => !value)}>{showPriorityEvidence ? "Hide evidence" : "View evidence"}</button>
          {showPriorityEvidence ? <div className="ask-lifeos-priority-evidence">{priorities.flatMap((priority, priorityIndex) => (priority.evidence || []).map((entry, evidenceIndex) => <article key={`${priorityIndex}-${evidenceIndex}-${entry.source_type}-${entry.source_id ?? entry.label}`}>
            <strong>{entry.label}</strong><span>{priority.title}</span>{entry.field ? <small>{entry.field}</small> : null}
          </article>))}</div> : null}
        </div> : null}
      </div> : null}
      {insight ? <div className="ask-lifeos-insight-list">
        <div className="ask-lifeos-insight-heading">
          <strong>{insight.kind.split("_").join(" ")}</strong>
          <span>{insight.context_limited ? "bounded view" : "verified state"}</span>
        </div>
        {insight.items.length ? insight.items.slice(0, 8).map((entry, index) => <article className={`ask-lifeos-insight-item insight-${entry.severity || "normal"}`} key={`${entry.type}-${entry.object_id ?? index}-${entry.title}`}>
          <div className="ask-lifeos-insight-rank">{index + 1}</div>
          <div className="ask-lifeos-insight-copy">
            <div className="ask-lifeos-insight-topline">
              <strong>{entry.title}</strong>
              {entry.project_title ? <span>{entry.project_title}</span> : entry.module_title ? <span>{entry.module_title}</span> : null}
            </div>
            <p>{entry.detail}</p>
            <div className="ask-lifeos-insight-meta">
              {entry.status ? <span>{entry.status}</span> : null}
              {entry.deadline ? <span>Due {entry.deadline}</span> : null}
            </div>
            {entry.action_hint ? <div className="ask-lifeos-insight-next"><b>Next:</b> {entry.action_hint}</div> : null}
          </div>
        </article>) : <div className="ask-lifeos-insight-empty">No matching items in the current trusted state.</div>}
        {insight.items.length > 8 ? <div className="ask-lifeos-activity-more">Showing the first 8 of {insight.items.length} items.</div> : null}
      </div> : null}
      {connections ? <div className="ask-lifeos-context-list">
        <div className="ask-lifeos-context-heading">
          <div><strong>Connected context</strong>{connections.resource ? <span>Tracing {connections.resource.label}</span> : <span>Choose a resource</span>}</div>
          <span>{connections.context_limited ? "bounded view" : "verified graph"}</span>
        </div>
        {connections.candidates.length ? <div className="ask-lifeos-context-candidates">
          {connections.candidates.map((candidate) => <button type="button" key={`${candidate.type}-${candidate.id}`} onClick={() => onReply(`Show connections for ${candidate.type} #${candidate.id}`)}>
            <span>{candidate.label}</span><em>{candidate.type.replace("_", " ")}</em>
          </button>)}
        </div> : null}
        {connections.connections.length ? <div className="ask-lifeos-context-grid">
          {connections.connections.slice(0, 10).map((connection) => <article className="ask-lifeos-context-card" key={`${connection.relation_type}-${connection.resource.type}-${connection.resource.id}`}>
            <div className="ask-lifeos-context-card-topline">
              <span className="ask-lifeos-context-relation">{connection.relation_label}</span>
              <span className="ask-lifeos-context-kind">{connection.resource.type.replace("_", " ")}</span>
            </div>
            {connection.resource.url ? <a href={connection.resource.url}>{connection.resource.label}</a> : <strong>{connection.resource.label}</strong>}
            {connection.resource.project_title ? <small>{connection.resource.project_title}</small> : null}
            {connection.reason ? <p>{connection.reason}</p> : null}
            {connection.provenance.type === "ask_lifeos" ? <div className="ask-lifeos-context-provenance">Preserved from confirmed Ask V-SPACE evidence</div> : null}
          </article>)}
        </div> : connections.candidates.length ? null : <div className="ask-lifeos-insight-empty">No connected context is currently recorded for this resource.</div>}
        {connections.connections.length > 10 ? <div className="ask-lifeos-activity-more">Showing the first 10 of {connections.connections.length} connections.</div> : null}
      </div> : null}
      {memory ? <div className="ask-lifeos-memory-list">
        <div className="ask-lifeos-memory-heading"><div><strong>Structured memory</strong><span>Inspectable · deletable · no hidden chat transcript</span></div><a href="/memory">Manage memory</a></div>
        {memory.items.length ? <div className="ask-lifeos-memory-grid">{memory.items.slice(0, 8).map((entry) => <article key={entry.id}>
          <div><span>{entry.type.replace(/_/g, " ")}</span>{entry.source.user_confirmed ? <em>You saved</em> : <em>V-SPACE derived</em>}</div>
          <strong>{entry.label}</strong>
          <p>{typeof entry.value.text === "string" ? entry.value.text : typeof entry.value.project_title === "string" ? entry.value.project_title : typeof entry.value.event_type === "string" ? entry.value.event_type : "Structured workspace memory"}</p>
        </article>)}</div> : <div className="ask-lifeos-insight-empty">No structured memory is currently saved.</div>}
      </div> : null}
      {grounded ? <div className="ask-lifeos-grounded-context">
        <div className="ask-lifeos-grounded-heading">
          <div><strong>Selected context</strong><span>{grounded.scope.label}</span></div>
          <span>{grounded.verified_grounding ? "grounded" : "not ready"}</span>
        </div>
        {grounded.sources.length ? <div className="ask-lifeos-grounded-sources">
          {grounded.sources.slice(0, 6).map((source, index) => <span key={`${groundedSourceLabel(source, index)}-${index}`}>{groundedSourceLabel(source, index)}</span>)}
        </div> : <div className="ask-lifeos-grounded-empty">No citation was returned for this answer.</div>}
      </div> : null}
      {memorySuggestion && showMemorySuggestion ? <div className="ask-lifeos-memory-suggestion">
        <div className="ask-lifeos-memory-suggestion-icon" aria-hidden="true">M</div>
        <div>
          <strong>Remember this {memorySuggestion.type === "current_focus" ? "focus" : "preference"}?</strong>
          <p>{memorySuggestion.value}</p>
          <span>{memorySuggestion.reason}</span>
          <div className="ask-lifeos-memory-suggestion-actions">
            <button type="button" className="primary" onClick={() => { onRemember(memorySuggestion); setShowMemorySuggestion(false); }}>Remember</button>
            <button type="button" onClick={() => setShowMemorySuggestion(false)}>Not now</button>
          </div>
        </div>
      </div> : null}
      {activity?.items?.length ? <div className="ask-lifeos-activity-list">
        <div className="ask-lifeos-activity-heading"><strong>Recent changes</strong><span>{activity.window.label}</span></div>
        {activity.items.slice(0, 8).map((event, index) => <article className="ask-lifeos-activity-item" key={`${event.event_type}-${event.object_type}-${event.object_id ?? index}-${event.occurred_at}`}>
          <div className="ask-lifeos-activity-dot" aria-hidden="true" />
          <div><div className="ask-lifeos-activity-topline"><strong>{event.title}</strong>{event.project_title ? <span>{event.project_title}</span> : null}</div>
            {event.summary ? <p>{event.summary}</p> : null}
            <time>{formatActivityTime(event.occurred_at)}</time>
          </div>
        </article>)}
        {activity.total_items > 8 ? <div className="ask-lifeos-activity-more">Showing the newest 8 of {activity.total_items} changes.</div> : null}
      </div> : null}
      {proposal ? <section className={`ask-lifeos-action-proposal proposal-${proposal.status}`}>
        <div className="ask-lifeos-action-icon" aria-hidden="true">✓</div>
        <div className="ask-lifeos-action-copy">
          <span>{proposal.status === "pending" ? "Confirmation required" : proposal.status === "confirmed" ? "Action completed" : proposal.status === "dismissed" ? "Dismissed" : proposal.status === "failed" ? "Action failed" : "Action in progress"}</span>
          <strong>{proposal.title}</strong>
          {proposal.reason ? <p>{proposal.reason}</p> : null}
          {proposal.action_type === "create_task" && typeof proposal.payload.title === "string" ? <div className="ask-lifeos-action-preview"><b>Task</b><span>{proposal.payload.title}</span></div> : null}
          {proposal.action_type === "create_note" && typeof proposal.payload.title === "string" ? <div className="ask-lifeos-action-preview"><b>Note</b><span>{proposal.payload.title}</span></div> : null}
          {proposal.failure_message ? <div className="ask-lifeos-action-error">{proposal.failure_message}</div> : null}
          {proposalError ? <div className="ask-lifeos-action-error">{proposalError}</div> : null}
          {proposal.status === "pending" ? <div className="ask-lifeos-action-controls">
            <button type="button" className="secondary" disabled={proposalBusy} onClick={() => void dismissProposal()}>Dismiss</button>
            <button type="button" className="primary" disabled={proposalBusy} onClick={() => void confirmProposal()}>{proposalBusy ? "Working…" : "Confirm action"}</button>
          </div> : null}
        </div>
      </section> : proposalError ? <div className="ask-lifeos-action-error standalone">{proposalError}</div> : null}
      {result ? <div className="ask-lifeos-answer-meta">
        {result.reasoning_tier ? <span className="ask-lifeos-model-chip">{askModelTierOptions.find((option) => option.value === result.reasoning_tier)?.label || result.reasoning_tier}</span> : null}
        {result.route.scope?.label ? <span className="ask-lifeos-scope-chip">{result.route.scope.label}</span> : null}
        {result.attention_level ? <span className={`ask-lifeos-attention attention-${result.attention_level}`}>{result.attention_level} attention</span> : null}
      </div> : null}
    </div>
  </div>;
}

export function AskLifeOSPage({ tutor = false }: { tutor?: boolean }) {
  const session = useSession();
  const [query, setQuery] = useState(() => (new URLSearchParams(location.search).get("q") || "").slice(0,1200));
  const [studyMode, setStudyMode] = useState("Explain");
  const threadRef = useRef<HTMLDivElement>(null);
  const [modelTier, setModelTier] = useState<AskModelTier>("normal");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversation, setConversation] = useState<ConversationItem[]>([]);
  const [clarificationContext, setClarificationContext] = useState<ClarificationContext | null>(null);
  const [contextOptions, setContextOptions] = useState<AskContextOptions | null>(null);
  const [selectedContext, setSelectedContext] = useState<AskContextOption | null>(null);
  const [contextPickerOpen, setContextPickerOpen] = useState(() => new URLSearchParams(location.search).get("contextPicker") === "1");
  const [contextSearch, setContextSearch] = useState("");
  const [memoryDraft, setMemoryDraft] = useState<ConversationMemorySuggestion | null>(null);
  const [memoryBusy, setMemoryBusy] = useState(false);
  const [memoryStatus, setMemoryStatus] = useState<string | null>(null);
  const nextId = useRef(1);
  const hasConversation = conversation.length > 0;
  const suggestions = useMemo(() => {
    const tailored = session.data?.user?.experience.ui.ask_prompts || [];
    return tutor ? ["Explain a difficult concept step by step", "Summarize the key ideas in my notes", "Give me practice questions on this topic", "Help me build a revision plan"] : [...new Set([...tailored, ...generalSuggestions])].slice(0, 4);
  }, [tutor, session.data?.user?.experience.primary_experience, session.data?.user?.experience.enabled_experiences.join("|")]);

  useEffect(() => {
    let cancelled = false;
    void apiGet<{ contexts: AskContextOptions }>("/api/v1/intelligence/context-options")
      .then((response) => {
        if (!cancelled) {
          setContextOptions(response.contexts);
          const params = new URLSearchParams(location.search);
          const ownedContext = Object.values(response.contexts.groups).flat().find(item => item.type === params.get("context_type") && item.id === Number(params.get("context_id")));
          if (ownedContext) setSelectedContext(ownedContext);
        }
      })
      .catch(() => {
        if (!cancelled) setContextOptions(null);
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => { threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "auto" }); }, [conversation.length, busy]);

  const statusText = useMemo(() => {
    if (busy) return selectedContext ? "Reading your selected context…" : "Checking your workspace…";
    if (selectedContext) return `Context locked to ${selectedContext.label}`;
    return "Your workspace. Your sources. Your decisions.";
  }, [busy, selectedContext]);

  const visibleContextGroups = useMemo(() => {
    const groups = contextOptions?.groups || {};
    const needle = contextSearch.trim().toLocaleLowerCase();
    return Object.entries(groups).map(([group, items]) => [
      group,
      needle
        ? items.filter((item) => `${item.label} ${item.subtitle || ""}`.toLocaleLowerCase().includes(needle))
        : items,
    ] as const).filter(([, items]) => items.length > 0);
  }, [contextOptions, contextSearch]);

  function chooseContext(context: AskContextOption | null) {
    setSelectedContext(context);
    setContextPickerOpen(false);
    setContextSearch("");
    setClarificationContext(null);
  }

  async function proposeMemory(text: string, contextSnapshot: AskContextOption | null = selectedContext) {
    if (!text.trim() || memoryBusy) return;
    setMemoryBusy(true);
    setMemoryStatus(null);
    try {
      const response = await apiPost<{ suggestion: ConversationMemorySuggestion | null; message?: string }>("/api/v1/intelligence/memory/propose", {
        text,
        selected_context: contextSnapshot,
      });
      if (response.suggestion) {
        setMemoryDraft(response.suggestion);
      } else {
        setMemoryStatus(response.message || "That message does not look like reusable memory.");
      }
    } catch (err) {
      setMemoryStatus(err instanceof ApiError ? err.message : "V-SPACE could not prepare that memory.");
    } finally {
      setMemoryBusy(false);
    }
  }

  async function saveMemory(suggestion: ConversationMemorySuggestion) {
    if (memoryBusy) return;
    setMemoryBusy(true);
    setMemoryStatus(null);
    try {
      await apiPost<{ memory: MemoryItem }>("/api/v1/intelligence/memory", {
        type: suggestion.type,
        label: suggestion.label,
        value: suggestion.value,
        project_id: suggestion.project_id ?? null,
      });
      setMemoryDraft(null);
      setMemoryStatus(`Remembered: ${suggestion.label}`);
    } catch (err) {
      setMemoryStatus(err instanceof ApiError ? err.message : "V-SPACE could not save that memory.");
    } finally {
      setMemoryBusy(false);
    }
  }

  async function submit(raw: string) {
    const text = raw.trim();
    if (!text || busy) return;

    const contextSnapshot = selectedContext ? { ...selectedContext } : null;
    const userItem: ConversationItem = { id: nextId.current++, role: "user", text, context: contextSnapshot };
    setConversation((items) => [...items, userItem]);
    setQuery("");
    setBusy(true);
    setError(null);
    setMemoryStatus(null);

    try {
      const result = await apiPost<AskLifeOSResponse>("/api/v1/intelligence/ask", {
        query: tutor ? `${studyMode === "Explain" ? "Explain this clearly, step by step, with examples" : studyMode === "Summarize" ? "Summarize the key ideas, definitions and takeaways" : studyMode === "Quiz me" ? "Create a short self-check quiz. Put each question under its own heading, and put answers in a separate answer key at the end" : studyMode === "Practice questions" ? "Give practice questions with worked solutions under separate headings" : "Create question-and-answer study flashcards, each under its own heading"}: ${text}. Use the selected material when provided, preserve source citations, and say when it does not support an answer.` : text,
        clarification_context: clarificationContext,
        selected_context: contextSnapshot,
        model_tier: modelTier,
      });
      const responseText = result.answer
        || result.clarification
        || (result.status === "unsupported_intent"
          ? "I understood what you are asking, but that V-SPACE intelligence workflow is not connected yet. I did not guess or use an unsafe fallback."
          : "V-SPACE could not produce a trusted answer for this request yet.");
      setConversation((items) => [...items, {
        id: nextId.current++,
        role: "assistant",
        text: responseText,
        result,
        context: contextSnapshot,
      }]);
      setClarificationContext(
        result.status === "clarification_required"
          ? { intent: result.route.intent }
          : null,
      );
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "V-SPACE could not process that request.";
      setError(message);
      setQuery(text);
    } finally {
      setBusy(false);
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void submit(query);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit(query);
    }
  }

  return <section className={`ask-lifeos-page ${tutor ? "vs-tutor-page" : ""}`}>
    <header className="ask-lifeos-hero">
      <div className="ask-lifeos-hero-copy">
        <span className="ask-lifeos-eyebrow"><Icon name={tutor ? "book" : "spark"}/>{tutor ? "Learn at your pace" : "Your connected intelligence"}</span>
        <h1>{tutor ? "Private Tutor" : "Ask V-SPACE"}</h1>
        <p>{tutor ? "Choose a topic or connect your study materials. Let’s make it click." : "Think it through. Find an answer. Take the next step."}</p>
      </div>
      <div className="ask-lifeos-safety-card">
        <span className="ask-lifeos-safety-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="M12 2 20 5v6c0 5.2-3.4 9.2-8 11-4.6-1.8-8-5.8-8-11V5l8-3Zm-1 13.2 5.3-5.3-1.4-1.4-3.9 3.9-1.9-1.9-1.4 1.4 3.3 3.3Z"/></svg>
        </span>
        <div><strong>You’re in control</strong><span>{statusText}</span></div>
      </div>
    </header>

    {tutor ? <div className="vs-tutor-modes" aria-label="Learning mode">{["Explain", "Summarize", "Quiz me", "Practice questions", "Flashcards"].map(mode => <button type="button" key={mode} disabled={busy} aria-pressed={studyMode === mode} className={studyMode === mode ? "active" : ""} onClick={() => setStudyMode(mode)}>{mode}</button>)}</div> : null}
    <div className={`ask-lifeos-workspace ${hasConversation ? "has-conversation" : ""}`}>
      <div className="ask-lifeos-thread" ref={threadRef} aria-live="polite">
        {!hasConversation ? <div className="ask-lifeos-empty">
          <div className="ask-lifeos-orb" aria-hidden="true"><BrandMark/></div>
          <h2>{tutor ? "What would you like to learn?" : "A clearer way forward."}</h2>
          <p>{tutor ? "Use the context selector below to choose a module, lecture, or document. Then tell me what you want to understand." : "Your projects, documents and plans, connected in one conversation. Ask naturally — I’ll check the context and help you move forward."}</p>
          <div className="ask-lifeos-suggestion-grid">
            {suggestions.map((item) => <button type="button" key={item} onClick={() => void submit(item)} disabled={busy}>
              <span>{item}</span><em>→</em>
            </button>)}
          </div>
        </div> : conversation.map((item) => item.role === "assistant"
          ? <AssistantMessage
              item={item}
              key={item.id}
              onReply={(text) => void submit(text)}
              onRemember={(suggestion) => setMemoryDraft(suggestion)}
            />
          : <div className="ask-lifeos-message user-message" key={item.id}>
              <div className="ask-lifeos-message-body">
                <div className="ask-lifeos-message-label">You</div>
                {item.context ? <div className="ask-lifeos-message-context"><span>{item.context.type}</span>{item.context.label}</div> : null}
                <div className="ask-lifeos-user-text">{item.text}</div>
                <div className="ask-lifeos-user-tools">
                  <button type="button" disabled={memoryBusy} onClick={() => void proposeMemory(item.text, item.context || null)}>Remember</button>
                </div>
              </div>
              <div className="ask-lifeos-avatar user-avatar" aria-hidden="true">Y</div>
            </div>)}
        {busy ? <div className="ask-lifeos-message assistant-message ask-lifeos-thinking">
          <div className="ask-lifeos-avatar lifeos-avatar"><BrandMark/></div>
          <div className="ask-lifeos-message-body"><div className="ask-lifeos-message-label">V-SPACE</div><div className="ask-lifeos-thinking-line"><span/><span/><span/>{selectedContext ? "Reading your selected context…" : "Checking your workspace…"}</div></div>
        </div> : null}
      </div>

      <form className="ask-lifeos-composer" onSubmit={handleSubmit}>
        {error ? <div className="ask-lifeos-error"><strong>Request failed</strong><span>{error}</span></div> : null}
        {memoryDraft ? <div className="ask-lifeos-inline-memory-confirm">
          <div className="ask-lifeos-inline-memory-copy">
            <span>{memoryDraft.type === "current_focus" ? "CURRENT FOCUS" : "PREFERENCE"}</span>
            <strong>Remember this for later?</strong>
            <p>{memoryDraft.value}</p>
            {memoryDraft.project_id ? <small>Scoped to the selected project.</small> : <small>Applies across V-SPACE.</small>}
          </div>
          <div className="ask-lifeos-inline-memory-actions">
            <button type="button" onClick={() => setMemoryDraft(null)} disabled={memoryBusy}>Cancel</button>
            <button type="button" className="primary" onClick={() => void saveMemory(memoryDraft)} disabled={memoryBusy}>{memoryBusy ? "Saving…" : "Remember"}</button>
          </div>
        </div> : null}
        {memoryStatus ? <div className="ask-lifeos-memory-status">{memoryStatus}</div> : null}

        <div className="ask-lifeos-context-toolbar">
          <button
            type="button"
            className={`ask-lifeos-context-trigger ${selectedContext ? "has-context" : ""}`}
            onClick={() => setContextPickerOpen((value) => !value)}
            aria-expanded={contextPickerOpen}
          >
            <span className="ask-lifeos-context-plus">+</span>
            <span>{selectedContext ? selectedContext.label : tutor ? "Choose study material" : "Your workspace"}</span>
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m5.8 7.5 4.2 4.2 4.2-4.2"/></svg>
          </button>
          {selectedContext ? <button type="button" className="ask-lifeos-context-clear" onClick={() => chooseContext(null)} aria-label="Clear selected context">×</button> : null}

          <label className="ask-lifeos-model-tier" title={askModelTierOptions.find((option) => option.value === modelTier)?.description}>
            <span>Model</span>
            <select value={modelTier} onChange={(event) => setModelTier(event.target.value as AskModelTier)} disabled={busy} aria-label="Ask V-SPACE model">
              {askModelTierOptions.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
            </select>
          </label>

          {contextPickerOpen ? <div className="ask-lifeos-context-picker">
            <div className="ask-lifeos-context-picker-head">
              <div><strong>Ask about</strong><span>Choose one verified V-SPACE context</span></div>
              <button type="button" onClick={() => setContextPickerOpen(false)} aria-label="Close context picker">×</button>
            </div>
            <input value={contextSearch} onChange={(event) => setContextSearch(event.target.value)} placeholder="Search projects, PDFs, modules…" autoFocus />
            <button type="button" className={`ask-lifeos-context-all ${!selectedContext ? "selected" : ""}`} onClick={() => chooseContext(null)}>
              <span className="ask-lifeos-context-option-icon">L</span>
              <span><strong>All V-SPACE</strong><small>Workspace-wide intelligence</small></span>
              {!selectedContext ? <em>✓</em> : null}
            </button>
            <div className="ask-lifeos-context-groups">
              {visibleContextGroups.map(([group, items]) => <section key={group}>
                <h4>{group}</h4>
                {items.map((item) => <button type="button" key={`${item.type}-${item.id}`} onClick={() => chooseContext(item)} className={selectedContext?.type === item.type && selectedContext.id === item.id ? "selected" : ""}>
                  <span className="ask-lifeos-context-option-icon">{item.type === "document" ? "D" : item.type === "project" ? "P" : item.type === "module" ? "M" : item.type === "lecture" ? "L" : "C"}</span>
                  <span><strong>{item.label}</strong><small>{item.subtitle || item.type}</small></span>
                  {selectedContext?.type === item.type && selectedContext.id === item.id ? <em>✓</em> : null}
                </button>)}
              </section>)}
              {!visibleContextGroups.length ? <div className="ask-lifeos-context-empty">No matching V-SPACE context.</div> : null}
            </div>
          </div> : null}
        </div>

        <div className="ask-lifeos-input-shell">
          <textarea
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={clarificationContext ? "Choose a project, or type all…" : selectedContext ? `Ask about ${selectedContext.label}…` : tutor ? "What do you want to learn?" : "Ask V-SPACE about your workspace…"}
            maxLength={1200}
            rows={2}
            disabled={busy}
            aria-label="Ask V-SPACE"
          />
          <button type="submit" className="ask-lifeos-send" disabled={busy || !query.trim()} aria-label="Send to V-SPACE">
            <Icon name="arrow"/>
          </button>
        </div>
        <div className="ask-lifeos-composer-footer">
          <span>{selectedContext ? `${selectedContext.type.replace("_", " ")} context · ` : ""}{askModelTierOptions.find((option) => option.value === modelTier)?.label} · Enter to send · Shift + Enter for a new line</span>
          <span>{query.length}/1200</span>
        </div>
      </form>
    </div>
  </section>;
}

