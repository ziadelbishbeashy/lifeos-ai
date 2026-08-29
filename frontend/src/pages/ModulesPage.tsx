import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";
import { ApiError } from "../api/client";
import { PageState } from "../components/NativeUi";
import { createModule, fetchModules, moduleKeys } from "../features/modules/api";

export function ModulesPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const query = useQuery({ queryKey: moduleKeys.all, queryFn: fetchModules, retry: false });

  const create = useMutation({
    mutationFn: createModule,
    onSuccess: async ({ item }) => {
      setShowCreate(false);
      setError(null);
      await queryClient.invalidateQueries({ queryKey: moduleKeys.all });
      window.location.assign(`/modules/${item.id}`);
    },
    onError: (value) => setError(value instanceof ApiError ? value.message : "The module could not be created."),
  });

  const modules = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (query.data?.items || []).filter((item) => {
      if (!needle) return true;
      return [item.title, item.subject, item.description].filter(Boolean).join(" ").toLowerCase().includes(needle);
    });
  }, [query.data, search]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    create.mutate({
      title: String(form.get("title") || "").trim(),
      subject: String(form.get("subject") || "").trim(),
      description: String(form.get("description") || "").trim(),
    });
  }

  if (query.isPending) return <PageState title="Opening Modules" text="Loading your learning workspaces…" />;
  if (query.isError) return <PageState title="Modules unavailable" text="LifeOS could not load your learning workspaces." error retry={() => query.refetch()} />;

  return <section className="modules-page">
    <header className="modules-page-header">
      <div>
        <span className="workspace-eyebrow">Knowledge-driven learning</span>
        <h1>Modules</h1>
        <p>Organize lectures, study material, notes, tasks, collections, and grounded AI without turning a course into a project.</p>
      </div>
      <button className="workspace-primary-button" type="button" onClick={() => setShowCreate((value) => !value)}>
        {showCreate ? "Close" : "+ New Module"}
      </button>
    </header>

    {error ? <div className="brain-alert is-error">{error}</div> : null}

    {showCreate ? <form className="module-create-card" onSubmit={submit}>
      <div className="module-form-grid">
        <label><span>Module name</span><input name="title" required maxLength={150} placeholder="e.g. Linear Algebra" /></label>
        <label><span>Subject</span><input name="subject" maxLength={150} placeholder="e.g. Mathematics" /></label>
      </div>
      <label><span>Description</span><textarea name="description" rows={3} placeholder="What are you learning in this module?" /></label>
      <div className="module-form-actions"><button className="workspace-primary-button" disabled={create.isPending}>{create.isPending ? "Creating…" : "Create Module"}</button></div>
    </form> : null}

    <div className="modules-toolbar">
      <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search modules" aria-label="Search modules" />
      <span>{modules.length} module{modules.length === 1 ? "" : "s"}</span>
    </div>

    {modules.length ? <div className="module-card-grid">
      {modules.map((item) => <article className="module-card" key={item.id}>
        <div className="module-card-top">
          <span className="module-card-icon">{item.title.slice(0, 1).toUpperCase()}</span>
          <div><span className="workspace-eyebrow">{item.subject || "Learning module"}</span><h2>{item.title}</h2></div>
          <span className={`module-status-pill ${item.status === "Archived" ? "is-archived" : ""}`}>{item.status}</span>
        </div>
        <p>{item.description || "A dedicated learning workspace for lectures, knowledge, and revision."}</p>
        <div className="module-metrics">
          <span><strong>{item.counts.lectures}</strong> Lectures</span>
          <span><strong>{item.counts.documents}</strong> Documents</span>
          <span><strong>{item.counts.tasks}</strong> Tasks</span>
        </div>
        <div className="module-card-footer">
          <span>{item.counts.notes} notes · {item.counts.collections} collections</span>
          <a className="workspace-primary-button" href={`/modules/${item.id}`}>Open Module</a>
        </div>
      </article>)}
    </div> : <div className="module-empty-state"><strong>{search ? "No matching modules" : "Create your first learning module"}</strong><p>{search ? "Try a different search." : "Use Modules for courses, subjects, interview preparation, or any body of knowledge that is not a project."}</p></div>}
  </section>;
}
