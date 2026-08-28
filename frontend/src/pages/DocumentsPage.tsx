import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { ApiError, apiGet, apiPostForm } from "../api/client";

type Document = {
  id: number;
  project_id: number | null;
  project: { id: number; title: string } | null;
  filename: string;
  version_label: string;
  uploaded_at: string | null;
  has_text: boolean;
  summary: string | null;
};

type Project = { id: number; title: string };
type Data = { items: Document[]; projects: Project[]; max_upload_bytes: number };

type IconName = "document" | "search" | "upload" | "compare" | "collection" | "project" | "spark" | "check" | "warning";

export function DocumentsPage() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [project, setProject] = useState("all");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState("newest");
  const [selectedFile, setSelectedFile] = useState("");

  const query = useQuery({
    queryKey: ["documents"],
    queryFn: () => apiGet<Data>("/api/v1/documents"),
  });

  const upload = useMutation({
    mutationFn: (form: FormData) => apiPostForm<any>("/api/v1/documents", form),
    onSuccess: async (result) => {
      setError(null);
      setSelectedFile("");
      setMessage(
        result.indexing_succeeded
          ? `Uploaded and indexed ${result.chunk_count} searchable chunks.`
          : "Uploaded. Search indexing may need attention.",
      );
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (failure) => {
      setMessage(null);
      setError(failure instanceof ApiError ? failure.message : "Upload failed.");
    },
  });

  if (query.isPending) {
    return <BrainState symbol="…" title="Opening Document Brain" text="Loading your project knowledge…" />;
  }

  if (query.isError || !query.data) {
    return (
      <BrainState
        symbol="!"
        title="Document Brain unavailable"
        text="Could not load your documents."
        action={<button className="workspace-secondary-button" onClick={() => query.refetch()}>Try again</button>}
      />
    );
  }

  const data = query.data;
  const textReady = data.items.filter((item) => item.has_text).length;
  const analysed = data.items.filter((item) => Boolean(item.summary)).length;
  const normalizedSearch = search.trim().toLowerCase();

  const filtered = data.items
    .filter((item) => {
      const searchable = [item.filename, item.project?.title, item.summary]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      if (normalizedSearch && !searchable.includes(normalizedSearch)) return false;
      if (project !== "all" && String(item.project_id ?? "") !== project) return false;
      if (status === "analysed" && !item.summary) return false;
      if (status === "ready" && (!item.has_text || Boolean(item.summary))) return false;
      if (status === "needs-text" && item.has_text) return false;
      return true;
    })
    .sort((a, b) => {
      if (sort === "name") return a.filename.localeCompare(b.filename);
      if (sort === "project") return (a.project?.title || "").localeCompare(b.project?.title || "");
      if (sort === "oldest") return String(a.uploaded_at || "").localeCompare(String(b.uploaded_at || ""));
      return String(b.uploaded_at || "").localeCompare(String(a.uploaded_at || ""));
    });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    upload.mutate(new FormData(event.currentTarget));
  }

  const hasFilters = Boolean(search.trim()) || project !== "all" || status !== "all";

  return (
    <section className="brain-library-page">
      <header className="brain-page-header">
        <div className="brain-page-title">
          <span className="brain-eyebrow">Grounded workspace</span>
          <h1>Document Brain</h1>
          <p>Search, analyse and question the PDFs connected to your projects.</p>
        </div>
        <div className="brain-header-actions">
          <a className="workspace-secondary-button" href="/documents/collections">
            <BrainIcon name="collection" />
            Collections
          </a>
          {data.items.length ? (
            <a className="workspace-secondary-button" href="/documents/compare">
              <BrainIcon name="compare" />
              Compare
            </a>
          ) : null}
          {data.projects.length ? (
            <a className="workspace-primary-button" href="#brain-upload">
              <BrainIcon name="upload" />
              Upload PDF
            </a>
          ) : (
            <a className="workspace-primary-button" href="/projects">Create project</a>
          )}
        </div>
      </header>

      <div className="brain-summary-strip" aria-label="Document Brain summary">
        <SummaryItem label="Documents" value={data.items.length} icon="document" />
        <SummaryItem label="Search ready" value={textReady} icon="check" />
        <SummaryItem label="Analysed" value={analysed} icon="spark" />
        <SummaryItem label="Projects" value={data.projects.length} icon="project" />
      </div>

      {error ? <div className="brain-alert is-error">{error}</div> : null}
      {message ? <div className="brain-alert is-success">{message}</div> : null}

      <div className="brain-workspace-grid">
        <main className="brain-library-panel">
          <div className="brain-panel-heading">
            <div>
              <span className="brain-eyebrow">Library</span>
              <h2>Your documents</h2>
            </div>
            <span className="brain-result-count">{filtered.length} of {data.items.length}</span>
          </div>

          {data.items.length ? (
            <>
              <div className="brain-toolbar">
                <label className="brain-search-control">
                  <BrainIcon name="search" />
                  <input
                    type="search"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search documents, projects, summaries…"
                    aria-label="Search documents"
                  />
                </label>
                <div className="brain-filter-row">
                  <label>
                    <span>Project</span>
                    <select value={project} onChange={(event) => setProject(event.target.value)}>
                      <option value="all">All projects</option>
                      {data.projects.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
                    </select>
                  </label>
                  <label>
                    <span>Status</span>
                    <select value={status} onChange={(event) => setStatus(event.target.value)}>
                      <option value="all">All statuses</option>
                      <option value="analysed">Analysed</option>
                      <option value="ready">Ready to analyse</option>
                      <option value="needs-text">Needs OCR</option>
                    </select>
                  </label>
                  <label>
                    <span>Sort</span>
                    <select value={sort} onChange={(event) => setSort(event.target.value)}>
                      <option value="newest">Newest</option>
                      <option value="oldest">Oldest</option>
                      <option value="name">Name A–Z</option>
                      <option value="project">Project A–Z</option>
                    </select>
                  </label>
                </div>
              </div>

              {filtered.length ? (
                <div className="brain-document-list">
                  {filtered.map((item) => <DocumentRow doc={item} key={item.id} />)}
                </div>
              ) : (
                <BrainState
                  compact
                  symbol="⌕"
                  title="No matching documents"
                  text="Try a different search or clear one of the filters."
                  action={hasFilters ? (
                    <button
                      type="button"
                      className="workspace-secondary-button"
                      onClick={() => { setSearch(""); setProject("all"); setStatus("all"); }}
                    >
                      Clear filters
                    </button>
                  ) : undefined}
                />
              )}
            </>
          ) : (
            <BrainState
              compact
              symbol="D"
              title="No documents yet"
              text="Upload your first project PDF to start building a searchable knowledge base."
              action={data.projects.length ? <a href="#brain-upload" className="workspace-primary-button">Upload first PDF</a> : undefined}
            />
          )}
        </main>

        <aside className="brain-side-column">
          {data.projects.length ? (
            <section className="brain-upload-card" id="brain-upload">
              <div className="brain-upload-heading">
                <span className="brain-upload-icon"><BrainIcon name="upload" /></span>
                <div>
                  <span className="brain-eyebrow">Add knowledge</span>
                  <h2>Upload a PDF</h2>
                </div>
              </div>
              <p className="brain-upload-intro">
                Connect a PDF to a project. LifeOS will extract its text and prepare it for search and analysis.
              </p>

              <form className="brain-upload-form" onSubmit={submit}>
                <label className="brain-field">
                  <span>Project</span>
                  <select name="project_id" required defaultValue="">
                    <option value="" disabled>Select a project</option>
                    {data.projects.map((item) => <option value={item.id} key={item.id}>{item.title}</option>)}
                  </select>
                </label>

                <label className={`brain-file-picker ${selectedFile ? "has-file" : ""}`}>
                  <input
                    type="file"
                    name="document"
                    accept=".pdf,application/pdf"
                    required
                    onChange={(event) => setSelectedFile(event.target.files?.[0]?.name || "")}
                  />
                  <span className="brain-file-icon">PDF</span>
                  <span className="brain-file-copy">
                    <strong>{selectedFile || "Choose a PDF"}</strong>
                    <small>{selectedFile ? "Ready to upload" : `PDF only · up to ${Math.round(data.max_upload_bytes / 1024 / 1024)} MB`}</small>
                  </span>
                  <span className="brain-file-action">Browse</span>
                </label>

                <button type="submit" className="workspace-primary-button brain-upload-button" disabled={upload.isPending}>
                  {upload.isPending ? "Uploading…" : "Upload & prepare"}
                </button>
              </form>

              <div className="brain-upload-steps" aria-label="Upload processing steps">
                <span><b>1</b> Private storage</span>
                <span><b>2</b> Text extraction</span>
                <span><b>3</b> Search index</span>
              </div>
            </section>
          ) : (
            <section className="brain-create-project-card">
              <span className="brain-upload-icon"><BrainIcon name="project" /></span>
              <h2>Create a project first</h2>
              <p>Documents belong to projects so analysis, tasks and evidence stay connected.</p>
              <a href="/projects" className="workspace-primary-button">Create project</a>
            </section>
          )}

          <section className="brain-help-card">
            <span className="brain-eyebrow">What you can do</span>
            <ul>
              <li><BrainIcon name="search" /><span><strong>Search the source</strong><small>Find exact passages inside extracted text.</small></span></li>
              <li><BrainIcon name="spark" /><span><strong>Analyse with AI</strong><small>Surface risks, requirements and next actions.</small></span></li>
              <li><BrainIcon name="check" /><span><strong>Verify answers</strong><small>Jump back to page-level evidence.</small></span></li>
            </ul>
          </section>
        </aside>
      </div>
    </section>
  );
}

function SummaryItem({ label, value, icon }: { label: string; value: number; icon: IconName }) {
  return (
    <article className="brain-summary-item">
      <span className="brain-summary-icon"><BrainIcon name={icon} /></span>
      <div><strong>{value}</strong><span>{label}</span></div>
    </article>
  );
}

function DocumentRow({ doc }: { doc: Document }) {
  const ui = doc.summary
    ? { key: "analysed", label: "Analysed" }
    : doc.has_text
      ? { key: "ready", label: "Ready to analyse" }
      : { key: "needs-text", label: "Needs OCR" };

  const date = doc.uploaded_at
    ? new Date(doc.uploaded_at).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" })
    : "Date unavailable";

  return (
    <article className="brain-document-row">
      <a className="brain-document-main" href={`/documents/${doc.id}`} aria-label={`Open ${doc.filename}`}>
        <span className="brain-document-icon"><BrainIcon name="document" /></span>
        <span className="brain-document-copy">
          <span className="brain-document-title-line">
            <strong title={doc.filename}>{doc.filename}</strong>
            <span className={`brain-status is-${ui.key}`}>{ui.label}</span>
          </span>
          <span className="brain-document-meta">
            <span>{doc.project?.title || "No project"}</span>
            <span>{doc.version_label}</span>
            <span>{date}</span>
          </span>
          <small>
            {doc.summary || (doc.has_text
              ? "Text extracted and ready for grounded analysis and questions."
              : "Stored safely, but readable embedded text was not found. OCR is required.")}
          </small>
        </span>
      </a>
      <div className="brain-document-actions">
        {doc.project ? <a href={`/projects/${doc.project.id}`} className="brain-row-link">Project</a> : null}
        <a href={`/documents/${doc.id}`} className="workspace-secondary-button">Open</a>
      </div>
    </article>
  );
}

function BrainState({ symbol, title, text, action, compact = false }: { symbol: string; title: string; text: string; action?: ReactNode; compact?: boolean }) {
  return (
    <div className={`brain-state ${compact ? "is-compact" : ""}`}>
      <span className="brain-state-symbol">{symbol}</span>
      <div>
        <h2>{title}</h2>
        <p>{text}</p>
        {action ? <div className="brain-state-action">{action}</div> : null}
      </div>
    </div>
  );
}

function BrainIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    document: <><path d="M7 3.5h6.5L17 7v13.5H7z"/><path d="M13.5 3.5V7H17M10 11h4M10 14h4M10 17h3"/></>,
    search: <><circle cx="11" cy="11" r="5.5"/><path d="m15.2 15.2 4 4"/></>,
    upload: <><path d="M12 16V5M8.5 8.5 12 5l3.5 3.5"/><path d="M5 15.5v4h14v-4"/></>,
    compare: <><path d="M8 5h11M15.5 2 19 5l-3.5 3M16 19H5M8.5 16 5 19l3.5 3"/></>,
    collection: <><rect x="4" y="5" width="16" height="5" rx="1.5"/><rect x="4" y="14" width="16" height="5" rx="1.5"/><path d="M8 7.5h8M8 16.5h8"/></>,
    project: <><path d="M4 7.5h6l1.5 2H20v9.5H4z"/><path d="M4 7.5V5h6l1.5 2.5"/></>,
    spark: <><path d="m12 3 1.2 3.8L17 8l-3.8 1.2L12 13l-1.2-3.8L7 8l3.8-1.2z"/><path d="m18 14 .7 2.3L21 17l-2.3.7L18 20l-.7-2.3L15 17l2.3-.7z"/></>,
    check: <path d="m5 12.5 4 4 10-10"/>,
    warning: <><path d="M12 4 3.8 19h16.4z"/><path d="M12 9v4M12 16.5h.01"/></>,
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}
