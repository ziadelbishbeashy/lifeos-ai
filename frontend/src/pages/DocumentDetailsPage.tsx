import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { apiGet, apiPost, apiPostForm, ApiError } from "../api/client";
import { PageState, VerifyButton, type Evidence } from "../components/NativeUi";
import { currentPath } from "../core/navigation";

type Suggestion = {
  id: number;
  title: string;
  description: string | null;
  priority: string;
  deadline: string | null;
  source: Evidence;
  status: string;
  lifecycle_label: string;
};

type Question = {
  id: number;
  question: string;
  answer: string | null;
  sources: any[];
  status: string;
  error_message: string | null;
  created_at: string | null;
};

type Detail = {
  document: any;
  analysis: any;
  latest_attempt: any;
  overview: any;
  type_workspace: any;
  analysis_experience: any;
  suggestions: Suggestion[];
  question_history: Question[];
  document_type_choices: any[];
  version_history: any;
  pdf_url: string;
};

type Detection = {
  document_type_key: string;
  document_type_label: string;
  confidence: string;
  reason: string;
};

type SearchHit = {
  rank: number;
  chunk_id: number | null;
  page_start: number | null;
  page_end: number | null;
  page_label: string;
  section: string;
  preview: string;
  exact_phrase: boolean;
  method_label: string;
  match_strength: string;
};

type SearchData = {
  query: string;
  mode: string;
  result_count: number;
  semantic_fallback: boolean;
  items: SearchHit[];
};

type Tab = "overview" | "details" | "pdf" | "search" | "actions" | "ask";
type DetailIconName = "overview" | "details" | "pdf" | "search" | "actions" | "ask";

function textOf(value: any) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return value.text || value.title || value.description || value.summary || value.question || value.risk || value.decision || JSON.stringify(value);
}

function sourceOf(value: any): Evidence {
  return value && typeof value === "object" ? (value.source || null) : null;
}

export function DocumentDetailsPage() {
  const id = Number(currentPath().match(/^\/documents\/(\d+)$/)?.[1] ?? NaN);
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("overview");
  const [error, setError] = useState<string | null>(null);
  const [detection, setDetection] = useState<Detection | null>(null);
  const [pdfPage, setPdfPage] = useState<number | null>(null);
  const [searchResults, setSearchResults] = useState<SearchData | null>(null);

  const query = useQuery({
    queryKey: ["document", id],
    queryFn: () => apiGet<Detail>(`/api/v1/documents/${id}`),
    enabled: Number.isFinite(id),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["document", id] });

  useEffect(() => {
    const openEvidence = (event: Event) => {
      const page = (event as CustomEvent).detail?.page;
      if (page) {
        setPdfPage(Number(page));
        setTab("pdf");
      }
    };
    window.addEventListener("lifeos-open-pdf", openEvidence);
    return () => window.removeEventListener("lifeos-open-pdf", openEvidence);
  }, []);

  const detect = useMutation({
    mutationFn: () => apiPost<{ detection: Detection }>(`/api/v1/documents/${id}/detect-type`),
    onSuccess: (result) => {
      setDetection(result.detection);
      setError(null);
    },
    onError: (failure) => setError(failure instanceof ApiError ? failure.message : "Type detection failed."),
  });

  const analyze = useMutation({
    mutationFn: (payload: any) => apiPost<Detail>(`/api/v1/documents/${id}/analyze`, payload),
    onSuccess: async () => {
      setDetection(null);
      setTab("overview");
      await refresh();
    },
    onError: (failure) => setError(failure instanceof ApiError ? failure.message : "Analysis failed."),
  });

  const ask = useMutation({
    mutationFn: (question: string) => apiPost<{ item: Question }>(`/api/v1/documents/${id}/questions`, { question }),
    onSuccess: refresh,
    onError: (failure) => setError(failure instanceof ApiError ? failure.message : "LifeOS could not answer this question."),
  });

  const suggestionAction = useMutation({
    mutationFn: ({ sid, action }: { sid: number; action: string }) => apiPost(`/api/v1/documents/${id}/suggestions/${sid}/${action}`),
    onSuccess: refresh,
    onError: (failure) => setError(failure instanceof ApiError ? failure.message : "Suggestion action failed."),
  });

  const version = useMutation({
    mutationFn: (form: FormData) => apiPostForm<any>(`/api/v1/documents/${id}/versions`, form),
    onSuccess: (result) => window.location.assign(`/documents/${result.item.id}`),
    onError: (failure) => setError(failure instanceof ApiError ? failure.message : "Version upload failed."),
  });

  const search = useMutation({
    mutationFn: (searchQuery: string) => apiGet<SearchData>(`/api/v1/documents/${id}/search?q=${encodeURIComponent(searchQuery)}`),
    onSuccess: (result) => {
      setSearchResults(result);
      setError(null);
    },
    onError: (failure) => setError(failure instanceof ApiError ? failure.message : "Document search failed."),
  });

  if (query.isPending) return <PageState title="Opening document" text="Loading grounded analysis and history…" />;
  if (query.isError || !query.data) {
    return <PageState title="Document unavailable" text="This document could not be loaded." error retry={() => query.refetch()} />;
  }

  const data = query.data;
  const experience = data.analysis_experience || {};
  const overview = data.overview || {};
  const analysis = overview.analysis || data.analysis?.insights || {};
  const sections = Array.isArray(data.type_workspace?.sections) ? data.type_workspace.sections : [];
  const docType = experience.type_label || data.analysis?.document_type || "Document";
  const attention = experience.attention || [];
  const recommendedActions = experience.actions || [];
  const suggestedQuestions = (experience.questions || []).length
    ? experience.questions
    : [
        { question: "What matters most in this document right now?" },
        { question: "What could block progress or success?" },
        { question: "What should I do next based on this document?" },
      ];

  function submitAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const question = String(form.get("question") || "").trim();
    if (question) ask.mutate(question);
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const searchQuery = String(form.get("search_query") || "").trim();
    if (searchQuery) search.mutate(searchQuery);
  }

  function submitVersion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    version.mutate(new FormData(event.currentTarget));
  }

  function startQuestion(question: string) {
    setTab("ask");
    window.setTimeout(() => {
      const input = document.querySelector<HTMLInputElement>('[name="question"]');
      if (input) {
        input.value = question;
        input.focus();
      }
    }, 0);
  }

  return (
    <section className="brain-detail-page">
      <div className="brain-breadcrumbs">
        <a href="/documents">Document Brain</a>
        <span>/</span>
        <span>{data.document.filename}</span>
      </div>

      <header className="brain-detail-header">
        <div className="brain-detail-title-wrap">
          <span className="brain-detail-file-icon">PDF</span>
          <div className="brain-detail-title">
            <div className="brain-detail-meta-line">
              <span className="brain-type-badge">{docType}</span>
              {data.document.project?.title ? <a href={`/projects/${data.document.project.id}`}>{data.document.project.title}</a> : null}
              <span>{data.document.version_label}</span>
            </div>
            <h1 title={data.document.filename}>{data.document.filename}</h1>
            <p>{data.analysis ? "Grounded analysis is ready. Review the evidence, actions and questions below." : "Detect the document type to create a grounded analysis."}</p>
          </div>
        </div>
        <div className="brain-detail-actions">
          <a className="workspace-secondary-button" href={`${data.pdf_url}?download=1`}>Download PDF</a>
          <button className="workspace-primary-button" onClick={() => detect.mutate()} disabled={detect.isPending}>
            {detect.isPending ? "Detecting…" : data.analysis ? "Re-analyse" : "Analyse document"}
          </button>
        </div>
      </header>

      {error ? <div className="brain-alert is-error">{error}</div> : null}

      {detection ? (
        <article className="brain-detection-card">
          <div className="brain-detection-copy">
            <span className="brain-eyebrow">Detected document type</span>
            <h2>{detection.document_type_label}</h2>
            <p>{detection.reason}</p>
            <span className="brain-confidence-badge">{detection.confidence} confidence</span>
          </div>
          <div className="brain-detection-actions">
            <label className="brain-field">
              <span>Confirm or change</span>
              <select id="confirmed-document-type" defaultValue={detection.document_type_key}>
                {data.document_type_choices.map((item: any) => (
                  <option key={item.key || item.value} value={item.key || item.value}>{item.label || item.name || item.value}</option>
                ))}
              </select>
            </label>
            <button
              className="workspace-primary-button"
              onClick={() => {
                const element = document.getElementById("confirmed-document-type") as HTMLSelectElement | null;
                analyze.mutate({
                  confirmed_document_type: element?.value || detection.document_type_key,
                  detected_document_type: detection.document_type_key,
                  detection_confidence: detection.confidence,
                });
              }}
              disabled={analyze.isPending}
            >
              {analyze.isPending ? "Analysing…" : "Confirm & analyse"}
            </button>
          </div>
        </article>
      ) : null}

      <nav className="brain-tabs" aria-label="Document workspace">
        {([
          ["overview", "Overview", "Document summary", "overview"],
          ["details", "Details", "Structured analysis", "details"],
          ["pdf", "PDF", "Open the source", "pdf"],
          ["search", "Search", "Find exact passages", "search"],
          ["actions", "Actions", data.suggestions.length ? `${data.suggestions.length} suggested` : "Suggested next steps", "actions"],
          ["ask", "Ask AI", "Grounded Q&A", "ask"],
        ] as const).map(([key, label, hint, icon]) => (
          <button key={key} type="button" className={`brain-tab brain-tab--${key} ${tab === key ? "active" : ""}`.trim()} onClick={() => setTab(key)} aria-label={label}>
            <span className="brain-tab-icon"><BrainDetailIcon name={icon} /></span>
            <span className="brain-tab-copy">
              <strong>{label}</strong>
              <small>{hint}</small>
            </span>
          </button>
        ))}
      </nav>

      {tab === "overview" ? (
        <div className="brain-detail-overview">
          {data.analysis ? (
            <>
              <article className="brain-focus-card">
                <div className="brain-focus-copy">
                  <span className="brain-eyebrow">{experience.status_label || "Analysis saved"}</span>
                  <h2>{experience.overview_title || `${docType} at a glance`}</h2>
                  <p>{data.analysis.summary || analysis.summary || "LifeOS has analysed this document."}</p>
                </div>
                <div className="brain-focus-now">
                  <span>Focus now</span>
                  <strong>{experience.focus || "Review the analysis and decide the next useful action."}</strong>
                  <VerifyButton source={experience.focus_source} />
                </div>
              </article>

              <div className="brain-overview-grid">
                <BrainSectionCard eyebrow="Needs attention" title="What matters now" count={experience.attention_count || attention.length}>
                  {attention.length ? (
                    <div className="brain-insight-list">
                      {attention.slice(0, 5).map((item: any, index: number) => (
                        <div className={`brain-insight-item is-${item.tone || "info"}`} key={index}>
                          <div>
                            <span>{item.label}</span>
                            <strong>{item.title}</strong>
                            {item.detail ? <p>{item.detail}</p> : null}
                          </div>
                          <VerifyButton source={item.source} />
                        </div>
                      ))}
                    </div>
                  ) : <DetailEmpty title="No urgent issues found" text="No grounded blocker was surfaced in the current analysis." />}
                </BrainSectionCard>

                <BrainSectionCard eyebrow="Recommended next actions" title="Move this forward" count={experience.action_count || recommendedActions.length}>
                  {recommendedActions.length ? (
                    <div className="brain-insight-list">
                      {recommendedActions.slice(0, 5).map((item: any, index: number) => (
                        <div className="brain-insight-item" key={index}>
                          <div>
                            <span>{item.priority || "Medium"} priority</span>
                            <strong>{item.title}</strong>
                            {item.detail ? <p>{item.detail}</p> : null}
                          </div>
                          <VerifyButton source={item.source} />
                        </div>
                      ))}
                    </div>
                  ) : <DetailEmpty title="No actions suggested" text="The analysis did not create an actionable recommendation yet." />}
                  <button className="brain-text-button" type="button" onClick={() => setTab("actions")}>Review all actions →</button>
                </BrainSectionCard>
              </div>

              <div className="brain-overview-grid is-secondary">
                <BrainSectionCard eyebrow="Explore" title="Ask useful questions">
                  <div className="brain-question-list">
                    {suggestedQuestions.slice(0, 6).map((item: any, index: number) => (
                      <button key={index} type="button" onClick={() => startQuestion(textOf(item))}>{textOf(item)}</button>
                    ))}
                  </div>
                </BrainSectionCard>

                <BrainSectionCard eyebrow="Structure" title="Inside this document">
                  {(experience.plan_sections || []).length ? (
                    <div className="brain-structure-list">
                      {(experience.plan_sections || []).slice(0, 6).map((item: any, index: number) => (
                        <button key={index} type="button" onClick={() => setTab("details")}>
                          <span>{item.label}</span>
                          <strong>{item.count}</strong>
                        </button>
                      ))}
                    </div>
                  ) : <DetailEmpty title="No structured sections" text="Detailed sections will appear after analysis." />}
                </BrainSectionCard>
              </div>
            </>
          ) : (
            <article className="brain-card brain-empty-analysis">
              <span className="brain-detail-file-icon">AI</span>
              <div>
                <span className="brain-eyebrow">Start here</span>
                <h2>Understand this document</h2>
                <p>Detect the PDF type, confirm it, then LifeOS can organise risks, requirements, actions and grounded evidence.</p>
                <button className="workspace-primary-button" onClick={() => detect.mutate()} disabled={detect.isPending}>
                  {detect.isPending ? "Detecting…" : "Analyse document"}
                </button>
              </div>
            </article>
          )}
        </div>
      ) : null}

      {tab === "details" ? (
        <div className="brain-detail-stack">
          {sections.length ? sections.map((section: any) => (
            <BrainSectionCard key={section.key} eyebrow="Detailed analysis" title={section.label} count={section.count || 0}>
              {section.value && typeof section.value === "object" && !Array.isArray(section.value) ? (
                <div className="brain-detail-item">
                  <p>{textOf(section.value)}</p>
                  <VerifyButton source={sourceOf(section.value)} />
                </div>
              ) : null}
              {Array.isArray(section.items) && section.items.length ? (
                <div className="brain-detail-item-list">
                  {section.items.map((item: any, index: number) => (
                    <div className="brain-detail-item" key={index}>
                      <div>
                        <strong>{item.title || item.risk || item.decision || item.question || item.description || `${section.label} ${index + 1}`}</strong>
                        <p>{item.detail || item.impact || item.why_it_matters || item.text || item.evidence || ""}</p>
                      </div>
                      <VerifyButton source={sourceOf(item)} />
                    </div>
                  ))}
                </div>
              ) : section.preview ? <p className="brain-muted-copy">{section.preview}</p> : null}
            </BrainSectionCard>
          )) : <DetailEmpty title="No detailed sections" text="Run an analysis to populate document-specific detail." />}
        </div>
      ) : null}

      {tab === "pdf" ? (
        <article className="brain-card brain-pdf-card">
          <div className="brain-card-heading">
            <div><span className="brain-eyebrow">Original evidence</span><h2>PDF viewer</h2></div>
            {pdfPage ? <span className="brain-count-badge">Page {pdfPage}</span> : null}
          </div>
          <iframe title={data.document.filename} src={`${data.pdf_url}${pdfPage ? `#page=${pdfPage}` : ""}`} className="brain-pdf-frame" />
        </article>
      ) : null}

      {tab === "search" ? (
        <article className="brain-card">
          <div className="brain-card-heading">
            <div><span className="brain-eyebrow">Search the source</span><h2>Find passages in this PDF</h2></div>
            {searchResults ? <span className="brain-count-badge">{searchResults.result_count} results</span> : null}
          </div>
          <form className="brain-composer" onSubmit={submitSearch}>
            <input name="search_query" placeholder="Search a word, phrase, or concept" maxLength={500} />
            <button className="workspace-primary-button" disabled={search.isPending}>{search.isPending ? "Searching…" : "Search"}</button>
          </form>
          {searchResults ? (
            <div className="brain-search-results">
              {searchResults.items.length ? searchResults.items.map((hit) => (
                <article className="brain-search-hit" key={`${hit.chunk_id}-${hit.rank}`}>
                  <header>
                    <div><span>{hit.page_label || `Result ${hit.rank}`}</span>{hit.section ? <strong>{hit.section}</strong> : null}</div>
                    <VerifyButton source={{ page: hit.page_start, section: hit.section, evidence: hit.preview }} />
                  </header>
                  <p>{hit.preview}</p>
                  <small>{hit.exact_phrase ? "Exact phrase · " : ""}{hit.method_label || hit.match_strength}</small>
                </article>
              )) : <DetailEmpty title="No matching passages" text="Try a broader phrase or a related concept." />}
            </div>
          ) : <p className="brain-muted-copy">Search works directly over the trusted extracted text. It finds evidence without generating an AI answer.</p>}
        </article>
      ) : null}

      {tab === "actions" ? (
        <article className="brain-card">
          <div className="brain-card-heading">
            <div><span className="brain-eyebrow">From insight to execution</span><h2>Suggested actions</h2></div>
            <span className="brain-count-badge">{data.suggestions.length}</span>
          </div>
          {data.suggestions.length ? (
            <div className="brain-action-list">
              {data.suggestions.map((suggestion) => (
                <div className="brain-action-row" key={suggestion.id}>
                  <div className="brain-action-copy">
                    <div><strong>{suggestion.title}</strong><span className="brain-priority-badge">{suggestion.priority}</span></div>
                    <p>{suggestion.description || "Suggested from this document"}</p>
                    <VerifyButton source={suggestion.source} />
                  </div>
                  <div className="brain-action-controls">
                    <span className="brain-status-text">{suggestion.lifecycle_label}</span>
                    {suggestion.status === "Pending" ? (
                      <div>
                        <button className="workspace-primary-button" onClick={() => suggestionAction.mutate({ sid: suggestion.id, action: "approve" })}>Create task</button>
                        <button className="workspace-secondary-button" onClick={() => suggestionAction.mutate({ sid: suggestion.id, action: "link" })}>Link existing</button>
                        <button className="brain-text-button is-danger" onClick={() => suggestionAction.mutate({ sid: suggestion.id, action: "reject" })}>Ignore</button>
                      </div>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          ) : <DetailEmpty title="No saved actions" text="Actionable findings created by analysis will appear here." />}
        </article>
      ) : null}

      {tab === "ask" ? (
        <article className="brain-card">
          <div className="brain-card-heading">
            <div><span className="brain-eyebrow">Grounded Q&A</span><h2>Ask this document</h2></div>
            <span className="brain-count-badge">{data.question_history.length} saved</span>
          </div>
          <form className="brain-composer" onSubmit={submitAsk}>
            <input name="question" placeholder="Ask a question grounded in this PDF" maxLength={2000} />
            <button className="workspace-primary-button" disabled={ask.isPending}>{ask.isPending ? "Searching…" : "Ask AI"}</button>
          </form>
          <div className="brain-qa-list">
            {data.question_history.length ? data.question_history.map((item) => (
              <article className="brain-qa-card" key={item.id}>
                <span className="brain-eyebrow">Question</span>
                <strong>{item.question}</strong>
                <p>{item.answer || item.error_message || "No saved answer."}</p>
                {item.sources?.length ? (
                  <div className="brain-qa-sources">
                    {item.sources.slice(0, 4).map((source: any, index: number) => (
                      <VerifyButton source={source} key={index} label={item.sources.length > 1 ? `Verify ${index + 1}` : "Verify"} />
                    ))}
                  </div>
                ) : null}
              </article>
            )) : <DetailEmpty title="No questions yet" text="Ask a grounded question above to start a document-specific history." />}
          </div>
        </article>
      ) : null}

      {data.document.is_current_version ? (
        <article className="brain-card brain-version-card">
          <div className="brain-card-heading">
            <div><span className="brain-eyebrow">Version history</span><h2>Document versions</h2></div>
            <span className="brain-count-badge">{data.version_history?.versions?.length || 1} version(s)</span>
          </div>
          <div className="brain-version-layout">
            {data.version_history?.versions?.length > 1 ? (
              <div className="brain-version-list">
                {data.version_history.versions.map((item: any) => (
                  <a key={item.id} href={`/documents/${item.id}`} className={item.id === data.document.id ? "active" : ""}>
                    <strong>{item.version_label}</strong><span>{item.filename}</span>
                  </a>
                ))}
              </div>
            ) : <p className="brain-muted-copy">This is the first version of the document.</p>}
            <form className="brain-version-upload" onSubmit={submitVersion}>
              <input type="file" name="document" accept="application/pdf,.pdf" required />
              <button className="workspace-secondary-button" disabled={version.isPending}>{version.isPending ? "Uploading…" : "Upload new version"}</button>
            </form>
          </div>
        </article>
      ) : null}
    </section>
  );
}

function BrainSectionCard({ eyebrow, title, count, children }: { eyebrow: string; title: string; count?: number; children: ReactNode }) {
  return (
    <article className="brain-card">
      <div className="brain-card-heading">
        <div><span className="brain-eyebrow">{eyebrow}</span><h2>{title}</h2></div>
        {typeof count === "number" ? <span className="brain-count-badge">{count}</span> : null}
      </div>
      {children}
    </article>
  );
}

function DetailEmpty({ title, text }: { title: string; text: string }) {
  return (
    <div className="brain-detail-empty">
      <strong>{title}</strong>
      <p>{text}</p>
    </div>
  );
}

function BrainDetailIcon({ name }: { name: DetailIconName }) {
  const paths: Record<DetailIconName, ReactNode> = {
    overview: <><path d="M4.5 5.5h6v6h-6z"/><path d="M13.5 5.5h6v6h-6z"/><path d="M4.5 14.5h6v6h-6z"/><path d="M13.5 14.5h6v6h-6z"/></>,
    details: <><path d="M8 7.5h11"/><path d="M8 12h11"/><path d="M8 16.5h11"/><path d="M4.5 7.5h.01"/><path d="M4.5 12h.01"/><path d="M4.5 16.5h.01"/></>,
    pdf: <><path d="M7 3.5h6.5L17 7v13.5H7z"/><path d="M13.5 3.5V7H17"/><path d="M9.5 12h5"/><path d="M9.5 15h5"/></>,
    search: <><circle cx="11" cy="11" r="5.5"/><path d="m15.2 15.2 4 4"/></>,
    actions: <><path d="M9 11.5 11 13.5l4-4"/><path d="M7 5.5h10"/><path d="M7 18.5h10"/><rect x="4" y="3.5" width="16" height="17" rx="2.5"/></>,
    ask: <><path d="M5 7.5a2.5 2.5 0 0 1 2.5-2.5h9A2.5 2.5 0 0 1 19 7.5v6A2.5 2.5 0 0 1 16.5 16H10l-4 3v-3H7.5A2.5 2.5 0 0 1 5 13.5z"/><path d="m12 7.5.9 2.4 2.6.1-2 1.6.7 2.4-2.2-1.4-2.2 1.4.7-2.4-2-1.6 2.6-.1z"/></>,
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}
