import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
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

export function DocumentsPage() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [project, setProject] = useState("all");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState("newest");

  const query = useQuery({
    queryKey: ["documents"],
    queryFn: () => apiGet<Data>("/api/v1/documents"),
  });

  const upload = useMutation({
    mutationFn: (form: FormData) => apiPostForm<any>("/api/v1/documents", form),
    onSuccess: async (result) => {
      setError(null);
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

  // Important: all React hooks are declared before any conditional return.
  // The previous implementation called useMemo only after the loading render,
  // which changed the number of hooks between renders and caused React to
  // crash with "Rendered more hooks than during the previous render".
  if (query.isPending) {
    return (
      <div className="db-empty-state">
        <span className="db-empty-icon">…</span>
        <div>
          <h2>Opening Document Brain</h2>
          <p>Loading your project knowledge…</p>
        </div>
      </div>
    );
  }

  if (query.isError || !query.data) {
    return (
      <div className="db-empty-state">
        <span className="db-empty-icon">!</span>
        <div>
          <h2>Document Brain unavailable</h2>
          <p>Could not load documents.</p>
          <button className="workspace-secondary-button" type="button" onClick={() => query.refetch()}>
            Try again
          </button>
        </div>
      </div>
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
      if (project !== "all" && item.project?.title.toLowerCase() !== project) return false;
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

  return (
    <div className="db-library">
      <section className="db-library-hero">
        <div className="db-library-hero-copy">
          <span className="db-kicker">Private project knowledge</span>
          <h1>Turn every PDF into a searchable, actionable workspace.</h1>
          <p>
            Upload project documents, extract their readable text, analyse requirements and risks,
            create tasks from detected actions, and ask grounded questions with page-level evidence.
          </p>
          <div className="db-hero-actions">
            {data.projects.length ? (
              <a href="#upload-document" className="workspace-primary-button">Upload a PDF</a>
            ) : (
              <a href="/projects" className="workspace-primary-button">Create a project</a>
            )}
            {data.items.length ? (
              <>
                <a href="/documents/compare" className="workspace-secondary-button">Compare documents</a>
                <a href="#document-library" className="workspace-secondary-button">Browse documents</a>
              </>
            ) : null}
          </div>
        </div>
        <div className="db-hero-visual" aria-hidden="true">
          <div className="db-hero-document">
            <span className="db-hero-document-type">PDF</span>
            <div><span/><span/><span/></div>
          </div>
          <div className="db-hero-orbit db-hero-orbit-analysis"><strong>AI</strong><small>Analysis</small></div>
          <div className="db-hero-orbit db-hero-orbit-search"><strong>{textReady}</strong><small>Ready</small></div>
          <div className="db-hero-orbit db-hero-orbit-answer"><strong>{analysed}</strong><small>Analysed</small></div>
        </div>
      </section>

      <section className="db-library-metrics" aria-label="Document Brain overview">
        <Metric icon="D" tone="purple" value={data.items.length} label="Total documents" />
        <Metric icon="T" tone="mint" value={textReady} label="Text ready" />
        <Metric icon="A" tone="amber" value={analysed} label="Analysed" />
        <Metric icon="P" tone="blue" value={data.projects.length} label="Projects" />
      </section>

      {error ? <div className="db-upload-error">{error}</div> : null}
      {message ? <div className="form-alert success">{message}</div> : null}

      {data.projects.length ? (
        <section id="upload-document" className="db-upload-section">
          <div className="db-section-heading">
            <div>
              <span className="db-kicker">Add knowledge</span>
              <h2>Upload a project PDF</h2>
              <p>LifeOS stores the file privately, extracts readable text, creates searchable chunks and prepares it for analysis.</p>
            </div>
            <span className="db-section-step">PDF only · Up to {Math.round(data.max_upload_bytes / 1024 / 1024)} MB</span>
          </div>
          <form className="db-upload-form" onSubmit={submit}>
            <div className="db-upload-grid">
              <div className="form-group db-upload-project">
                <label>Connect to project</label>
                <select name="project_id" required defaultValue="">
                  <option value="">Select a project</option>
                  {data.projects.map((item) => <option value={item.id} key={item.id}>{item.title}</option>)}
                </select>
                <small>Documents inherit the selected project's ownership and access rules.</small>
              </div>
              <div className="db-upload-file-column">
                <label className="db-dropzone">
                  <input type="file" name="document" accept=".pdf,application/pdf" required />
                  <span className="db-dropzone-icon">PDF</span>
                  <span className="db-dropzone-copy">
                    <strong>Drop a PDF here or browse</strong>
                    <small>The original filename is shown in LifeOS while storage uses a private, unique key.</small>
                  </span>
                  <span className="db-dropzone-browse">Choose file</span>
                </label>
              </div>
            </div>
            <div className="db-upload-footer">
              <div className="db-upload-guidance">
                <span><b>1</b>Private storage</span>
                <span><b>2</b>Automatic text extraction</span>
                <span><b>3</b>Searchable hybrid index</span>
              </div>
              <button type="submit" className="workspace-primary-button" disabled={upload.isPending}>
                {upload.isPending ? "Uploading…" : "Upload and prepare"}
              </button>
            </div>
          </form>
        </section>
      ) : (
        <section className="db-empty-state db-project-required">
          <span className="db-empty-icon">P</span>
          <div>
            <h2>Create a project first</h2>
            <p>Every document belongs to a project so LifeOS can keep ownership and actions connected.</p>
            <a href="/projects" className="workspace-primary-button">Create project</a>
          </div>
        </section>
      )}

      <section id="document-library" className="db-library-section">
        <div className="db-section-heading">
          <div>
            <span className="db-kicker">Project knowledge</span>
            <h2>Your document library</h2>
            <p>Search, filter and open any PDF to view its analysis, actions and grounded question history.</p>
          </div>
          {data.items.length ? <span className="db-visible-count"><strong>{filtered.length}</strong> shown</span> : null}
        </div>

        {data.items.length ? (
          <>
            <div className="db-library-toolbar">
              <label className="db-search-field">
                <span className="db-search-icon">⌕</span>
                <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search documents or projects" />
              </label>
              <div className="db-library-filters">
                <label>
                  <select value={project} onChange={(event) => setProject(event.target.value)}>
                    <option value="all">All projects</option>
                    {data.projects.map((item) => <option key={item.id} value={item.title.toLowerCase()}>{item.title}</option>)}
                  </select>
                </label>
                <label>
                  <select value={status} onChange={(event) => setStatus(event.target.value)}>
                    <option value="all">All statuses</option>
                    <option value="analysed">Analysed</option>
                    <option value="ready">Ready to analyse</option>
                    <option value="needs-text">Needs OCR</option>
                  </select>
                </label>
                <label>
                  <select value={sort} onChange={(event) => setSort(event.target.value)}>
                    <option value="newest">Newest first</option>
                    <option value="oldest">Oldest first</option>
                    <option value="name">Name A–Z</option>
                    <option value="project">Project A–Z</option>
                  </select>
                </label>
              </div>
            </div>
            <div className="db-document-grid" data-view="grid">
              {filtered.map((item) => <DocumentCard doc={item} key={item.id} />)}
            </div>
            {!filtered.length ? (
              <div className="db-empty-state">
                <span className="db-empty-icon">⌕</span>
                <div><h2>No matching documents</h2><p>Try a different search or filter.</p></div>
              </div>
            ) : null}
          </>
        ) : (
          <div className="db-empty-state">
            <span className="db-empty-icon">D</span>
            <div><h2>No documents yet</h2><p>Upload a PDF to begin building grounded project knowledge.</p></div>
          </div>
        )}
      </section>
    </div>
  );
}

function Metric({ icon, tone, value, label }: { icon: string; tone: string; value: number; label: string }) {
  return (
    <article>
      <span className={`db-metric-icon db-metric-${tone}`}>{icon}</span>
      <div><strong>{value}</strong><span>{label}</span></div>
    </article>
  );
}

function DocumentCard({ doc }: { doc: Document }) {
  const ui = doc.summary
    ? { key: "analysed", label: "Analysed" }
    : doc.has_text
      ? { key: "ready", label: "Ready to analyse" }
      : { key: "needs-text", label: "Needs OCR" };

  return (
    <article className="db-document-card">
      <div className="db-document-card-top">
        <div className="db-file-mark">PDF</div>
        <div className="db-document-card-heading">
          <span className="db-project-pill">{doc.project?.title || "No project"}</span>
          <span className="db-version-library-badge is-current">{doc.version_label}</span>
          <h3 title={doc.filename}>{doc.filename}</h3>
        </div>
        <span className={`db-status-badge db-status-${ui.key}`}>{ui.label}</span>
      </div>
      <p className="db-document-preview">
        {doc.summary || (doc.has_text
          ? "Text extracted and ready for analysis and grounded questions."
          : "This PDF is stored safely, but no readable embedded text was found. OCR support is required before analysis or questions.")}
      </p>
      <div className="db-document-card-footer">
        <span className="db-document-date">
          {doc.uploaded_at
            ? new Date(doc.uploaded_at).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" })
            : "Date unavailable"}
        </span>
        <div className="db-document-actions">
          <a href={`/documents/${doc.id}`} className="workspace-primary-button">Open</a>
          {doc.project ? <a href={`/projects/${doc.project.id}`} className="workspace-secondary-button">Project</a> : null}
        </div>
      </div>
    </article>
  );
}
