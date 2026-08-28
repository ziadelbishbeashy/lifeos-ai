import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiDelete, apiGet, apiPost } from "../api/client";
import { PageState } from "../components/NativeUi";

type DocumentSummary = {
  id: number;
  project_id: number | null;
  filename: string;
  version_label: string;
  has_text: boolean;
  summary: string | null;
};

type CollectionSummary = {
  id: number;
  name: string;
  description: string | null;
  document_count: number;
  created_at: string | null;
  updated_at: string | null;
};

type CollectionQuestion = {
  id: number;
  collection_id: number;
  question: string;
  answer: string | null;
  sources: Array<{
    source_id?: number;
    document_id?: number;
    filename?: string;
    page?: number | string | null;
    section?: string | null;
    evidence?: string | null;
    content_type?: string;
    table_id?: number | null;
  }>;
  status: string;
  error_message: string | null;
  created_at: string | null;
};

type CollectionDetail = CollectionSummary & { documents: DocumentSummary[] };
type CollectionResponse = { item: CollectionDetail; question_history: CollectionQuestion[] };
type DocumentsResponse = { items: DocumentSummary[] };

export function DocumentCollectionsPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const collectionsQuery = useQuery({
    queryKey: ["document-collections"],
    queryFn: () => apiGet<{ items: CollectionSummary[] }>("/api/v1/document-collections"),
  });

  const documentsQuery = useQuery({
    queryKey: ["documents"],
    queryFn: () => apiGet<DocumentsResponse>("/api/v1/documents"),
  });

  useEffect(() => {
    const items = collectionsQuery.data?.items || [];
    if (!items.length) {
      setSelectedId(null);
      return;
    }
    if (selectedId == null || !items.some((item) => item.id === selectedId)) {
      setSelectedId(items[0].id);
    }
  }, [collectionsQuery.data, selectedId]);

  const detailQuery = useQuery({
    queryKey: ["document-collection", selectedId],
    queryFn: () => apiGet<CollectionResponse>(`/api/v1/document-collections/${selectedId}`),
    enabled: selectedId != null,
  });

  const refreshCollections = async (collectionId?: number | null) => {
    await queryClient.invalidateQueries({ queryKey: ["document-collections"] });
    if (collectionId != null) {
      await queryClient.invalidateQueries({ queryKey: ["document-collection", collectionId] });
    }
  };

  const createCollection = useMutation({
    mutationFn: (payload: { name: string; description: string }) =>
      apiPost<{ item: CollectionDetail }>("/api/v1/document-collections", payload),
    onSuccess: async (result) => {
      setError(null);
      setMessage(`Created “${result.item.name}”.`);
      setSelectedId(result.item.id);
      await refreshCollections(result.item.id);
    },
    onError: (failure) => {
      setMessage(null);
      setError(failure instanceof ApiError ? failure.message : "Could not create the collection.");
    },
  });

  const addDocument = useMutation({
    mutationFn: (documentId: number) =>
      apiPost<{ item: CollectionDetail }>(`/api/v1/document-collections/${selectedId}/documents`, { document_id: documentId }),
    onSuccess: async () => {
      setError(null);
      setMessage("Document added to the collection.");
      await refreshCollections(selectedId);
    },
    onError: (failure) => setError(failure instanceof ApiError ? failure.message : "Could not add the document."),
  });

  const removeDocument = useMutation({
    mutationFn: (documentId: number) =>
      apiDelete<{ item: CollectionDetail }>(`/api/v1/document-collections/${selectedId}/documents/${documentId}`),
    onSuccess: async () => {
      setError(null);
      setMessage("Document removed from the collection.");
      await refreshCollections(selectedId);
    },
    onError: (failure) => setError(failure instanceof ApiError ? failure.message : "Could not remove the document."),
  });

  const askCollection = useMutation({
    mutationFn: (question: string) =>
      apiPost<{ item: CollectionQuestion }>(`/api/v1/document-collections/${selectedId}/questions`, { question }),
    onSuccess: async () => {
      setError(null);
      setMessage(null);
      await refreshCollections(selectedId);
    },
    onError: (failure) => setError(failure instanceof ApiError ? failure.message : "LifeOS could not answer this collection question."),
  });

  const deleteCollection = useMutation({
    mutationFn: () => apiDelete<{ deleted: boolean; name: string }>(`/api/v1/document-collections/${selectedId}`),
    onSuccess: async (result) => {
      setError(null);
      setMessage(`Deleted “${result.name}”.`);
      setSelectedId(null);
      await refreshCollections();
    },
    onError: (failure) => setError(failure instanceof ApiError ? failure.message : "Could not delete the collection."),
  });

  const current = detailQuery.data?.item;
  const allDocuments = documentsQuery.data?.items || [];
  const currentIds = new Set((current?.documents || []).map((item) => item.id));
  const availableDocuments = allDocuments.filter(
    (item) => item.has_text && !currentIds.has(item.id),
  );

  function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") || "").trim();
    const description = String(form.get("description") || "").trim();
    if (!name) return;
    createCollection.mutate({ name, description });
    event.currentTarget.reset();
  }

  function submitAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const documentId = Number(form.get("document_id"));
    if (Number.isFinite(documentId) && documentId > 0) addDocument.mutate(documentId);
  }

  function submitAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input = event.currentTarget.elements.namedItem("question") as HTMLInputElement | null;
    const question = String(input?.value || "").trim();
    if (!question) return;
    askCollection.mutate(question);
    if (input) input.value = "";
  }

  if (collectionsQuery.isPending || documentsQuery.isPending) {
    return <PageState title="Opening collections" text="Loading your document groups…" />;
  }

  if (collectionsQuery.isError || documentsQuery.isError) {
    return <PageState title="Collections unavailable" text="LifeOS could not load Document Collections." error retry={() => { collectionsQuery.refetch(); documentsQuery.refetch(); }} />;
  }

  const collections = collectionsQuery.data?.items || [];

  return (
    <section className="brain-library-page brain-collections-page">
      <header className="brain-page-header">
        <div className="brain-page-title">
          <span className="brain-eyebrow">Multi-document intelligence</span>
          <h1>Document Collections</h1>
          <p>Group PDFs from different projects and ask one grounded question across all of them.</p>
        </div>
        <div className="brain-header-actions">
          <a className="workspace-secondary-button" href="/documents">Back to Document Brain</a>
        </div>
      </header>

      {error ? <div className="brain-alert is-error">{error}</div> : null}
      {message ? <div className="brain-alert is-success">{message}</div> : null}

      <div className="brain-collections-layout">
        <aside className="brain-card brain-collection-sidebar">
          <div className="brain-card-heading">
            <div><span className="brain-eyebrow">Saved groups</span><h2>Collections</h2></div>
            <span className="brain-count-badge">{collections.length}</span>
          </div>

          <form className="brain-collection-create" onSubmit={submitCreate}>
            <input name="name" placeholder="Collection name" maxLength={150} required />
            <textarea name="description" placeholder="Optional purpose or description" rows={2} maxLength={4000} />
            <button className="workspace-primary-button" disabled={createCollection.isPending}>
              {createCollection.isPending ? "Creating…" : "Create collection"}
            </button>
          </form>

          <div className="brain-collection-list">
            {collections.map((item) => (
              <button
                type="button"
                key={item.id}
                className={`brain-collection-list-item ${selectedId === item.id ? "active" : ""}`}
                onClick={() => setSelectedId(item.id)}
              >
                <strong>{item.name}</strong>
                <span>{item.document_count} document{item.document_count === 1 ? "" : "s"}</span>
              </button>
            ))}
            {!collections.length ? <p className="brain-muted-copy">Create your first collection to study several documents together.</p> : null}
          </div>
        </aside>

        <main className="brain-collection-main">
          {selectedId == null ? (
            <article className="brain-card"><div className="brain-detail-empty"><strong>No collection selected</strong><p>Create a collection, then add readable PDFs to it.</p></div></article>
          ) : detailQuery.isPending ? (
            <article className="brain-card"><div className="brain-detail-empty"><strong>Opening collection…</strong><p>Loading documents and grounded question history.</p></div></article>
          ) : detailQuery.isError || !current ? (
            <article className="brain-card"><div className="brain-detail-empty"><strong>Collection unavailable</strong><p>LifeOS could not load this collection.</p></div></article>
          ) : (
            <>
              <article className="brain-card">
                <div className="brain-card-heading brain-collection-heading">
                  <div>
                    <span className="brain-eyebrow">Collection</span>
                    <h2>{current.name}</h2>
                    {current.description ? <p className="brain-muted-copy">{current.description}</p> : null}
                  </div>
                  <button
                    className="brain-text-button is-danger"
                    type="button"
                    disabled={deleteCollection.isPending}
                    onClick={() => {
                      if (window.confirm(`Delete “${current.name}”? The PDFs themselves will not be deleted.`)) deleteCollection.mutate();
                    }}
                  >
                    Delete collection
                  </button>
                </div>

                <form className="brain-collection-add" onSubmit={submitAdd}>
                  <select name="document_id" disabled={!availableDocuments.length || addDocument.isPending} defaultValue="">
                    <option value="" disabled>{availableDocuments.length ? "Choose a readable PDF" : "No more readable PDFs available"}</option>
                    {availableDocuments.map((document) => <option key={document.id} value={document.id}>{document.filename}</option>)}
                  </select>
                  <button className="workspace-secondary-button" disabled={!availableDocuments.length || addDocument.isPending}>Add document</button>
                </form>

                <div className="brain-collection-documents">
                  {(current.documents || []).map((document) => (
                    <div className="brain-collection-document" key={document.id}>
                      <div>
                        <a href={`/documents/${document.id}`}><strong>{document.filename}</strong></a>
                        <span>{document.version_label || "Current version"}</span>
                      </div>
                      <button className="brain-text-button is-danger" type="button" onClick={() => removeDocument.mutate(document.id)} disabled={removeDocument.isPending}>Remove</button>
                    </div>
                  ))}
                  {!current.documents?.length ? <div className="brain-detail-empty"><strong>No documents yet</strong><p>Add at least one readable PDF before asking a collection question.</p></div> : null}
                </div>
              </article>

              <article className="brain-card">
                <div className="brain-card-heading">
                  <div><span className="brain-eyebrow">Grounded across files</span><h2>Ask this collection</h2></div>
                  <span className="brain-count-badge">{detailQuery.data?.question_history?.length || 0} saved</span>
                </div>
                <form className="brain-composer" onSubmit={submitAsk}>
                  <input name="question" placeholder="Ask across all documents in this collection" maxLength={2000} disabled={!current.documents?.length} />
                  <button className="workspace-primary-button" disabled={!current.documents?.length || askCollection.isPending}>{askCollection.isPending ? "Searching…" : "Ask AI"}</button>
                </form>

                <div className="brain-qa-list">
                  {(detailQuery.data?.question_history || []).map((item) => (
                    <article className="brain-qa-card" key={item.id}>
                      <span className="brain-eyebrow">Question</span>
                      <strong>{item.question}</strong>
                      <p>{item.answer || item.error_message || "No saved answer."}</p>
                      {item.sources?.length ? (
                        <div className="brain-collection-source-list">
                          {item.sources.map((source, index) => (
                            <details className="brain-collection-source" key={`${item.id}-${index}`}>
                              <summary>
                                Source {source.source_id || index + 1} · {source.filename || "Document"}{source.page ? ` · Page ${source.page}` : ""}{source.content_type === "table" ? " · Table" : ""}
                              </summary>
                              {source.section ? <strong>{source.section}</strong> : null}
                              {source.evidence ? <blockquote>{source.evidence}</blockquote> : null}
                              {source.document_id ? <a className="workspace-secondary-button compact" href={`/documents/${source.document_id}?tab=pdf${source.page ? `&page=${encodeURIComponent(String(source.page).split("-")[0])}` : ""}`}>Open source document</a> : null}
                            </details>
                          ))}
                        </div>
                      ) : null}
                    </article>
                  ))}
                  {!detailQuery.data?.question_history?.length ? <div className="brain-detail-empty"><strong>No questions yet</strong><p>Ask something that may require evidence from one or several PDFs.</p></div> : null}
                </div>
              </article>
            </>
          )}
        </main>
      </div>
    </section>
  );
}
