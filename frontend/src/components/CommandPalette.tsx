import { useId, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../api/client";
import { Icon, Modal, type IconName } from "./VSpaceUi";

type Command = { title: string; href: string; group: string; icon: IconName; detail?: string };
const pages: Command[] = [
  { title: "Dashboard", href: "/dashboard", group: "Pages", icon: "dashboard" },
  { title: "Ask V-SPACE", href: "/ask", group: "Pages", icon: "spark" },
  { title: "Smart Planner", href: "/planner", group: "Pages", icon: "calendar" },
  { title: "Projects", href: "/projects", group: "Pages", icon: "projects" },
  { title: "Tasks", href: "/tasks", group: "Pages", icon: "tasks" },
  { title: "Document Brain", href: "/documents", group: "Pages", icon: "documents" },
  { title: "Private Tutor", href: "/tutor", group: "Pages", icon: "book" },
  { title: "Focus Studio", href: "/focus", group: "Pages", icon: "focus" },
  { title: "Automations", href: "/automations", group: "Pages", icon: "automation" },
  { title: "Notes", href: "/notes", group: "Pages", icon: "notes" },
  { title: "Modules", href: "/modules", group: "Pages", icon: "book" },
  { title: "Collections", href: "/documents/collections", group: "Pages", icon: "documents" },
  { title: "Memory", href: "/memory", group: "Pages", icon: "memory" },
  { title: "Analytics", href: "/analytics", group: "Pages", icon: "analytics" },
  { title: "Notifications", href: "/notifications/history", group: "Pages", icon: "bell" },
  { title: "Settings", href: "/settings", group: "Pages", icon: "settings" },
];
const actions: Command[] = [
  { title: "Create project", href: "/projects#new-project", group: "Quick actions", icon: "projects", detail: "Connect a goal, tasks and knowledge" },
  { title: "Create task", href: "/tasks#new-task", group: "Quick actions", icon: "tasks", detail: "Capture your next action" },
  { title: "Create note", href: "/notes#new-note", group: "Quick actions", icon: "notes", detail: "Keep an idea close" },
  { title: "Upload document", href: "/documents#brain-upload", group: "Quick actions", icon: "upload", detail: "Add a PDF to your knowledge" },
  { title: "Plan my day", href: "/planner", group: "Quick actions", icon: "calendar", detail: "Preview a schedule before accepting it" },
];
type IndexedItem = { id: number; title?: string; filename?: string; project?: { title: string } | null };
const sources: { endpoint: string; group: string; icon: IconName; link: (id: number) => string }[] = [
  { endpoint: "/api/v1/projects", group: "Projects", icon: "projects", link: id => `/projects/${id}` },
  { endpoint: "/api/v1/tasks", group: "Tasks", icon: "tasks", link: id => `/tasks?task=${id}` },
  { endpoint: "/api/v1/documents", group: "Documents", icon: "documents", link: id => `/documents/${id}` },
  { endpoint: "/api/v1/notes", group: "Notes", icon: "notes", link: id => `/notes/${id}` },
];
export function CommandPalette({ onClose, createOnly = false, modulesVisible = true, moduleLabel = "Modules" }: { onClose: () => void; createOnly?: boolean; modulesVisible?: boolean; moduleLabel?: string }) {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(0);
  const listId = useId();
  const index = useQuery({
    queryKey: ["vspace", "command-index"], enabled: !createOnly, staleTime: 30_000, retry: false,
    queryFn: async () => {
      const results = await Promise.allSettled(sources.map(s => apiGet<{ items: IndexedItem[] }>(s.endpoint)));
      const items: Command[] = [];
      let unavailable = 0;
      results.forEach((result, i) => {
        if (result.status === "rejected" || !Array.isArray(result.value?.items)) { unavailable++; return; }
        result.value.items.forEach(item => { if (item.title || item.filename) items.push({ title: item.title || item.filename || "Untitled", href: sources[i].link(item.id), icon: sources[i].icon, group: sources[i].group, detail: item.project?.title }); });
      });
      return { items, unavailable };
    },
  });
  const results = useMemo(() => {
    const visiblePages = pages.filter(p => modulesVisible || p.href !== "/modules").map(p => p.href === "/modules" ? { ...p, title: moduleLabel } : p);
    const all = createOnly ? actions : [...visiblePages, ...actions, ...(index.data?.items || [])];
    const needle = search.trim().toLocaleLowerCase();
    return (needle ? all.filter(item => `${item.title} ${item.group} ${item.detail || ""}`.toLocaleLowerCase().includes(needle)) : createOnly ? actions : visiblePages).slice(0, 40);
  }, [search, createOnly, index.data, modulesVisible, moduleLabel]);
  const active = Math.min(selected, Math.max(0, results.length - 1));
  return <Modal title={createOnly ? "Create something" : "Search your workspace"} onClose={onClose} className="vs-command-palette">
    <div className="vs-command-search"><Icon name="search"/><input autoFocus data-autofocus value={search} placeholder={createOnly ? "What would you like to create?" : "Search projects, tasks, documents and pages…"} aria-label="Search workspace" role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls={listId} aria-activedescendant={results.length ? `${listId}-${active}` : undefined} onChange={e => { setSearch(e.target.value); setSelected(0); }} onKeyDown={e => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); const next = (active + (e.key === "ArrowDown" ? 1 : -1) + results.length) % Math.max(1, results.length); setSelected(next); document.getElementById(`${listId}-${next}`)?.scrollIntoView({ block: "nearest" }); }
      if (e.key === "Enter" && results[active]) { e.preventDefault(); window.location.assign(results[active].href); }
    }}/><kbd>esc</kbd></div>
    <div className="vs-command-results" role="listbox" id={listId} aria-label="Search results">{results.map((item, i) => <a id={`${listId}-${i}`} key={`${item.group}-${item.href}`} href={item.href} role="option" aria-selected={active === i} className={`vs-command-item ${active === i ? "selected" : ""}`} onMouseMove={() => setSelected(i)}><span className="vs-command-icon"><Icon name={item.icon}/></span><span><strong>{item.title}</strong><small>{item.detail || item.group}</small></span><span className="vs-command-group">{item.group}</span><Icon name="arrow"/></a>)}{!results.length ? <div className="vs-command-empty">No matches for “{search}”. Try a shorter search.</div> : null}</div>
    {!createOnly && index.isPending ? <p className="vs-command-status" role="status">Loading your workspace items…</p> : null}
    {index.data?.unavailable ? <p className="vs-command-status">Some workspace items couldn’t load. <button type="button" onClick={() => void index.refetch()}>Try again</button></p> : null}
    <footer className="vs-command-footer"><span>↑ ↓ to explore</span><span>Enter to open</span><span>Esc to close</span></footer>
  </Modal>;
}
