import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";
import { ApiError } from "../api/client";
import type { Lecture, ModuleQuestion } from "../api/types";
import { PageState } from "../components/NativeUi";
import { pathId } from "../core/navigation";
import {
  askModule,
  createLecture,
  deleteLecture,
  deleteModule,
  fetchModule,
  linkModuleDocument,
  linkModuleResource,
  moduleKeys,
  unlinkModuleDocument,
  unlinkModuleResource,
  uploadModuleDocument,
} from "../features/modules/api";
import { ContextConnectionsPanel } from "../components/ContextConnectionsPanel";

function SourceList({ question }: { question: ModuleQuestion }) {
  if (!question.sources?.length) return null;
  return <div className="module-source-list">
    {question.sources.map((source, index) => <details className="module-source" key={`${question.id}-${index}`}>
      <summary>Source {source.source_id || index + 1} · {source.filename || "Document"}{source.page ? ` · Page ${source.page}` : ""}{source.content_type === "table" ? " · Table" : ""}</summary>
      {source.section ? <strong>{source.section}</strong> : null}
      {source.evidence ? <blockquote>{source.evidence}</blockquote> : null}
      {source.document_id ? <a className="workspace-secondary-button compact" href={`/documents/${source.document_id}?tab=pdf${source.page ? `&page=${encodeURIComponent(String(source.page).split("-")[0])}` : ""}`}>Open source</a> : null}
    </details>)}
  </div>;
}

function QuestionHistory({ items, empty }: { items: ModuleQuestion[]; empty: string }) {
  return <div className="module-question-history">
    {items.map((item) => <article className="module-question-card" key={item.id}>
      <span className="workspace-eyebrow">Question</span>
      <strong>{item.question}</strong>
      <p>{item.answer || item.error_message || "No saved answer."}</p>
      <SourceList question={item} />
    </article>)}
    {!items.length ? <div className="module-inline-empty">{empty}</div> : null}
  </div>;
}

function lectureLabel(lecture: Lecture) {
  return lecture.lecture_number ? `Lecture ${lecture.lecture_number}` : "Lecture";
}

export function ModuleDetailsPage() {
  const moduleId = pathId(/^\/modules\/(\d+)$/);
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [activeLectureId, setActiveLectureId] = useState<number | null>(null);
  const query = useQuery({
    queryKey: moduleKeys.detail(moduleId || 0),
    queryFn: () => fetchModule(moduleId!),
    enabled: moduleId != null,
    retry: false,
  });

  async function refresh() {
    if (moduleId == null) return;
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: moduleKeys.detail(moduleId) }),
      queryClient.invalidateQueries({ queryKey: moduleKeys.all }),
    ]);
  }

  function fail(value: unknown) {
    setMessage(null);
    setError(value instanceof ApiError ? value.message : "LifeOS could not complete that module action.");
  }

  const addLecture = useMutation({
    mutationFn: (payload: { title: string; lecture_number?: number; lecture_date?: string; topics?: string }) => createLecture(moduleId!, payload),
    onSuccess: async () => { setError(null); setMessage("Lecture added."); await refresh(); },
    onError: fail,
  });
  const removeLecture = useMutation({
    mutationFn: (lectureId: number) => deleteLecture(moduleId!, lectureId),
    onSuccess: async () => { setError(null); setMessage("Lecture removed. Linked resources stayed in the module."); setActiveLectureId(null); await refresh(); },
    onError: fail,
  });
  const addDocument = useMutation({
    mutationFn: ({ documentId, lectureId }: { documentId: number; lectureId: number | null }) => linkModuleDocument(moduleId!, documentId, lectureId),
    onSuccess: async () => { setError(null); setMessage("Document linked to module."); await refresh(); },
    onError: fail,
  });
  const uploadDocument = useMutation({
    mutationFn: ({ file, lectureId }: { file: File; lectureId: number | null }) => uploadModuleDocument(moduleId!, file, lectureId),
    onSuccess: async () => { setError(null); setMessage("PDF uploaded and linked to module."); await refresh(); },
    onError: fail,
  });
  const removeDocument = useMutation({
    mutationFn: (documentId: number) => unlinkModuleDocument(moduleId!, documentId),
    onSuccess: async () => { setError(null); setMessage("Document removed from this module. The PDF was not deleted."); await refresh(); },
    onError: fail,
  });
  const linkResource = useMutation({
    mutationFn: ({ kind, id, lectureId }: { kind: "notes" | "tasks" | "collections"; id: number; lectureId: number | null }) => linkModuleResource(moduleId!, kind, id, lectureId),
    onSuccess: async () => { setError(null); setMessage("Resource linked to module."); await refresh(); },
    onError: fail,
  });
  const unlinkResource = useMutation({
    mutationFn: ({ kind, id }: { kind: "notes" | "tasks" | "collections"; id: number }) => unlinkModuleResource(moduleId!, kind, id),
    onSuccess: async () => { setError(null); setMessage("Resource removed from this module."); await refresh(); },
    onError: fail,
  });
  const ask = useMutation({
    mutationFn: ({ question, lectureId }: { question: string; lectureId: number | null }) => askModule(moduleId!, question, lectureId),
    onSuccess: async ({ reused_existing }) => { setError(null); setMessage(reused_existing ? "Loaded the existing grounded answer." : "Grounded answer saved."); await refresh(); },
    onError: fail,
  });
  const removeModule = useMutation({
    mutationFn: () => deleteModule(moduleId!),
    onSuccess: () => window.location.assign("/modules"),
    onError: fail,
  });

  const data = query.data;
  const module = data?.item;
  const linkedDocumentIds = useMemo(() => new Set((module?.documents || []).map((item) => item.id)), [module?.documents]);
  const linkedNoteIds = useMemo(() => new Set((module?.notes || []).map((item) => item.id)), [module?.notes]);
  const linkedTaskIds = useMemo(() => new Set((module?.tasks || []).map((item) => item.id)), [module?.tasks]);
  const linkedCollectionIds = useMemo(() => new Set((module?.collections || []).map((item) => item.id)), [module?.collections]);
  const activeLecture = module?.lectures.find((item) => item.id === activeLectureId) || null;

  if (moduleId == null) return <PageState title="Module unavailable" text="The module address is invalid." error />;
  if (query.isPending) return <PageState title="Opening module" text="Loading lectures and study context…" />;
  if (query.isError || !module || !data) return <PageState title="Module unavailable" text="LifeOS could not load this learning workspace." error retry={() => query.refetch()} />;

  function submitLecture(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const title = String(form.get("title") || "").trim();
    if (!title) return;
    const numberText = String(form.get("lecture_number") || "").trim();
    addLecture.mutate({
      title,
      lecture_number: numberText ? Number(numberText) : undefined,
      lecture_date: String(form.get("lecture_date") || "") || undefined,
      topics: String(form.get("topics") || "").trim() || undefined,
    });
    event.currentTarget.reset();
  }

  function submitAsk(event: FormEvent<HTMLFormElement>, lectureId: number | null) {
    event.preventDefault();
    const input = event.currentTarget.elements.namedItem("question") as HTMLInputElement | null;
    const question = String(input?.value || "").trim();
    if (!question) return;
    ask.mutate({ question, lectureId });
    if (input) input.value = "";
  }

  const moduleLectures = module.lectures;

  function lectureSelect(name = "lecture_id") {
    return <select name={name} defaultValue=""><option value="">Whole module</option>{moduleLectures.map((lecture) => <option key={lecture.id} value={lecture.id}>{lectureLabel(lecture)} · {lecture.title}</option>)}</select>;
  }

  return <section className="module-workspace-page">
    <header className="module-workspace-header">
      <div>
        <a className="module-back-link" href="/modules">← Modules</a>
        <span className="workspace-eyebrow">{module.subject || "Learning module"}</span>
        <h1>{module.title}</h1>
        <p>{module.description || "Organize lectures, knowledge, revision, and grounded study material in one workspace."}</p>
      </div>
      <div className="module-header-actions">
        <span className="module-status-pill">{module.status}</span>
        <button type="button" className="brain-text-button is-danger" disabled={removeModule.isPending} onClick={() => { if (window.confirm(`Delete “${module.title}”? Linked documents, notes, tasks and collections will remain in LifeOS.`)) removeModule.mutate(); }}>Delete module</button>
      </div>
    </header>

    {error ? <div className="brain-alert is-error">{error}</div> : null}
    {message ? <div className="brain-alert is-success">{message}</div> : null}

    <div className="module-summary-strip">
      <span><strong>{module.counts.lectures}</strong> lectures</span>
      <span><strong>{module.counts.documents}</strong> documents</span>
      <span><strong>{module.counts.notes}</strong> notes</span>
      <span><strong>{module.counts.tasks}</strong> study tasks</span>
      <span><strong>{module.counts.collections}</strong> collections</span>
    </div>

    <div className="module-workspace-grid">
      <aside className="module-lecture-panel">
        <div className="module-section-heading"><div><span className="workspace-eyebrow">Course structure</span><h2>Lectures</h2></div><span>{module.lectures.length}</span></div>
        <form className="module-lecture-form" onSubmit={submitLecture}>
          <div className="module-lecture-number-row"><input name="lecture_number" type="number" min={1} placeholder="#" /><input name="title" required maxLength={180} placeholder="Lecture title" /></div>
          <input name="lecture_date" type="date" />
          <input name="topics" placeholder="Topics, comma separated" />
          <button className="workspace-secondary-button" disabled={addLecture.isPending}>{addLecture.isPending ? "Adding…" : "+ Add lecture"}</button>
        </form>
        <div className="module-lecture-list">
          {module.lectures.map((lecture) => <button type="button" key={lecture.id} className={`module-lecture-item ${activeLectureId === lecture.id ? "active" : ""}`} onClick={() => setActiveLectureId((value) => value === lecture.id ? null : lecture.id)}>
            <span>{lecture.lecture_number || "•"}</span><div><strong>{lecture.title}</strong><small>{lecture.status}{lecture.topics ? ` · ${lecture.topics}` : ""}</small></div>
          </button>)}
          {!module.lectures.length ? <div className="module-inline-empty">Add lectures to give the module a learning structure.</div> : null}
        </div>
      </aside>

      <main className="module-main-column">
        {activeLecture ? <article className="module-panel module-active-lecture">
          <div className="module-section-heading"><div><span className="workspace-eyebrow">{lectureLabel(activeLecture)}</span><h2>{activeLecture.title}</h2><p>{activeLecture.summary || activeLecture.topics || "No lecture summary yet."}</p></div><button type="button" className="brain-text-button is-danger" onClick={() => { if (window.confirm(`Remove “${activeLecture.title}”? Its linked resources will stay in the module.`)) removeLecture.mutate(activeLecture.id); }}>Remove lecture</button></div>
          <div className="module-lecture-resource-chips">
            <span>{module.documents.filter((item) => item.lecture_id === activeLecture.id).length} documents</span>
            <span>{module.notes.filter((item) => item.lecture_id === activeLecture.id).length} notes</span>
            <span>{module.tasks.filter((item) => item.lecture_id === activeLecture.id).length} tasks</span>
          </div>
          <form className="module-ask-form" onSubmit={(event) => submitAsk(event, activeLecture.id)}>
            <input name="question" maxLength={2000} placeholder={`Ask only ${activeLecture.title}`} />
            <button className="workspace-primary-button" disabled={ask.isPending || !module.documents.some((item) => item.lecture_id === activeLecture.id)}>{ask.isPending ? "Searching…" : "Ask Lecture"}</button>
          </form>
          <QuestionHistory items={data.lecture_question_history[String(activeLecture.id)] || []} empty="No grounded lecture questions yet." />
        </article> : null}

        <article className="module-panel module-ask-panel">
          <div className="module-section-heading"><div><span className="workspace-eyebrow">Grounded learning intelligence</span><h2>Ask this Module</h2><p>Search across the PDFs linked to this module using the same grounded Document Brain pipeline.</p></div><span>{data.question_history.length} saved</span></div>
          <form className="module-ask-form" onSubmit={(event) => submitAsk(event, null)}>
            <input name="question" maxLength={2000} placeholder={`Ask across ${module.title}`} />
            <button className="workspace-primary-button" disabled={ask.isPending || !module.documents.length}>{ask.isPending ? "Searching…" : "Ask Module"}</button>
          </form>
          <QuestionHistory items={data.question_history} empty="Ask a question once the module has at least one searchable document." />
        </article>

        <article className="module-panel">
          <div className="module-section-heading"><div><span className="workspace-eyebrow">Study material</span><h2>Documents</h2><p>Attach an existing PDF or upload lecture material directly to the module.</p></div><span>{module.documents.length}</span></div>
          <div className="module-resource-actions">
            <form onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); const id = Number(form.get("document_id")); const lectureId = Number(form.get("lecture_id")) || null; if (id) addDocument.mutate({ documentId: id, lectureId }); }}>
              <select name="document_id" defaultValue=""><option value="" disabled>Choose existing PDF</option>{data.available.documents.filter((item) => !linkedDocumentIds.has(item.id)).map((item) => <option key={item.id} value={item.id}>{item.filename}</option>)}</select>
              {lectureSelect()}
              <button className="workspace-secondary-button" disabled={addDocument.isPending}>Link PDF</button>
            </form>
            <form onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); const file = form.get("document"); const lectureId = Number(form.get("lecture_id")) || null; if (file instanceof File && file.size) uploadDocument.mutate({ file, lectureId }); }}>
              <input name="document" type="file" accept="application/pdf,.pdf" required />
              {lectureSelect()}
              <button className="workspace-primary-button" disabled={uploadDocument.isPending}>{uploadDocument.isPending ? "Uploading…" : "Upload PDF"}</button>
            </form>
          </div>
          <div className="module-resource-list">
            {module.documents.map((document) => <div className="module-resource-row" key={document.id}><div><a href={`/documents/${document.id}`}><strong>{document.filename}</strong></a><span>{document.lecture_id ? module.lectures.find((item) => item.id === document.lecture_id)?.title || "Lecture" : "Whole module"} · {document.version_label}</span></div><button type="button" className="brain-text-button is-danger" onClick={() => removeDocument.mutate(document.id)}>Remove</button></div>)}
            {!module.documents.length ? <div className="module-inline-empty">No module documents yet.</div> : null}
          </div>
        </article>

        <div className="module-secondary-grid">
          <article className="module-panel">
            <div className="module-section-heading"><div><span className="workspace-eyebrow">Knowledge</span><h2>Notes</h2></div><span>{module.notes.length}</span></div>
            <form className="module-compact-link-form" onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); const id = Number(form.get("resource_id")); const lectureId = Number(form.get("lecture_id")) || null; if (id) linkResource.mutate({ kind: "notes", id, lectureId }); }}><select name="resource_id" defaultValue=""><option value="" disabled>Choose note</option>{data.available.notes.filter((item) => !linkedNoteIds.has(item.id)).map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select>{lectureSelect()}<button className="workspace-secondary-button">Add</button></form>
            <div className="module-resource-list compact">{module.notes.map((note) => <div className="module-resource-row" key={note.id}><div><a href={`/notes/${note.id}`}><strong>{note.title}</strong></a><span>{note.lecture_id ? module.lectures.find((item) => item.id === note.lecture_id)?.title || "Lecture" : "Whole module"}</span></div><button type="button" className="brain-text-button is-danger" onClick={() => unlinkResource.mutate({ kind: "notes", id: note.id })}>Remove</button></div>)}{!module.notes.length ? <div className="module-inline-empty">No linked notes.</div> : null}</div>
          </article>

          <article className="module-panel">
            <div className="module-section-heading"><div><span className="workspace-eyebrow">Study actions</span><h2>Tasks</h2></div><span>{module.tasks.length}</span></div>
            <form className="module-compact-link-form" onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); const id = Number(form.get("resource_id")); const lectureId = Number(form.get("lecture_id")) || null; if (id) linkResource.mutate({ kind: "tasks", id, lectureId }); }}><select name="resource_id" defaultValue=""><option value="" disabled>Choose task</option>{data.available.tasks.filter((item) => !linkedTaskIds.has(item.id)).map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select>{lectureSelect()}<button className="workspace-secondary-button">Add</button></form>
            <div className="module-resource-list compact">{module.tasks.map((task) => <div className="module-resource-row" key={task.id}><div><strong>{task.title}</strong><span>{task.status}{task.lecture_id ? ` · ${module.lectures.find((item) => item.id === task.lecture_id)?.title || "Lecture"}` : ""}</span></div><button type="button" className="brain-text-button is-danger" onClick={() => unlinkResource.mutate({ kind: "tasks", id: task.id })}>Remove</button></div>)}{!module.tasks.length ? <div className="module-inline-empty">No study tasks linked.</div> : null}</div>
          </article>
        </div>

        <ContextConnectionsPanel resourceType="module" resourceId={module.id} />

        <article className="module-panel">
          <div className="module-section-heading"><div><span className="workspace-eyebrow">Focused document groups</span><h2>Collections</h2><p>Collections narrow retrieval; Modules provide the broader learning structure.</p></div><span>{module.collections.length}</span></div>
          <form className="module-compact-link-form collection" onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); const id = Number(form.get("resource_id")); if (id) linkResource.mutate({ kind: "collections", id, lectureId: null }); }}><select name="resource_id" defaultValue=""><option value="" disabled>Choose collection</option>{data.available.collections.filter((item) => !linkedCollectionIds.has(item.id)).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button className="workspace-secondary-button">Link collection</button><a className="workspace-secondary-button" href="/documents/collections">Open Collections</a></form>
          <div className="module-resource-list compact">{module.collections.map((collection) => <div className="module-resource-row" key={collection.id}><div><strong>{collection.name}</strong><span>{collection.document_count} document{collection.document_count === 1 ? "" : "s"}</span></div><button type="button" className="brain-text-button is-danger" onClick={() => unlinkResource.mutate({ kind: "collections", id: collection.id })}>Remove</button></div>)}{!module.collections.length ? <div className="module-inline-empty">No linked collections.</div> : null}</div>
        </article>
      </main>
    </div>
  </section>;
}
