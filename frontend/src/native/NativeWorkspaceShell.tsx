import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import type { ProactiveNotificationData, User } from "../api/types";
import { apiPost } from "../api/client";
import { FrontendErrorBoundary } from "../components/FrontendErrorBoundary";
import { CommandPalette } from "../components/CommandPalette";
import { BrandMark, Icon, type IconName } from "../components/VSpaceUi";
import { logout } from "../auth/session";
import { navigate } from "../core/navigation";

export type NativeSection = "dashboard" | "projects" | "modules" | "tasks" | "notes" | "focus" | "planner" | "analytics" | "notifications" | "documents" | "intelligence" | "tutor" | "memory" | "automations" | "settings";
type NavItem = { key: NativeSection; href: string; label: string; icon: IconName };
const groups: { label: string; items: NavItem[] }[] = [
  { label: "Workspace", items: [
    { key: "dashboard", href: "/dashboard", label: "Dashboard", icon: "dashboard" },
    { key: "projects", href: "/projects", label: "Projects", icon: "projects" },
    { key: "tasks", href: "/tasks", label: "Tasks", icon: "tasks" },
    { key: "planner", href: "/planner", label: "Smart Planner", icon: "calendar" },
  ] },
  { label: "Intelligence", items: [
    { key: "intelligence", href: "/ask", label: "Ask V-SPACE", icon: "spark" },
    { key: "documents", href: "/documents", label: "Document Brain", icon: "documents" },
    { key: "tutor", href: "/tutor", label: "Private Tutor", icon: "book" },
    { key: "memory", href: "/memory", label: "Memory", icon: "memory" },
  ] },
  { label: "Productivity", items: [
    { key: "focus", href: "/focus", label: "Focus Studio", icon: "focus" },
    { key: "automations", href: "/automations", label: "Automations", icon: "automation" },
    { key: "analytics", href: "/analytics", label: "Analytics", icon: "analytics" },
  ] },
  { label: "Knowledge", items: [
    { key: "notes", href: "/notes", label: "Notes", icon: "notes" },
    { key: "modules", href: "/modules", label: "Modules", icon: "book" },
  ] },
];
function stored(key: string) { try { return localStorage.getItem(key); } catch { return null; } }
function save(key: string, value: string) { try { localStorage.setItem(key, value); } catch { /* Storage can be blocked. */ } }

export function NativeWorkspaceShell({ user, active, children }: { user: User; active: NativeSection; children: ReactNode }) {
  const [profileOpen, setProfileOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => stored("vspace-sidebar-collapsed") === "true");
  const [command, setCommand] = useState<"search" | "create" | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">(() => stored("lifeos-theme") === "light" ? "light" : "dark");
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const profileRef = useRef<HTMLDivElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const mobileButtonRef = useRef<HTMLButtonElement>(null);
  const initial = (user.name || user.email || "V").trim().slice(0, 1).toUpperCase();
  const experience = user.experience;
  const pageTitle = active === "settings" ? "Settings" : active === "notifications" ? "Notifications" : active === "modules" ? experience.ui.module_label : groups.flatMap(g => g.items).find(item => item.key === active)?.label || "Workspace";
  const proactiveQuery = useQuery({
    queryKey: ["lifeos-proactive-notifications"],
    queryFn: () => apiPost<{ proactive: ProactiveNotificationData }>("/api/v1/intelligence/proactive/refresh"),
    refetchInterval: 60_000, refetchOnWindowFocus: true, retry: false,
  });
  const unread = proactiveQuery.data?.proactive?.counts.unread ?? 0;

  useEffect(() => {
    document.body.classList.add("app-body", "studio-theme");
    document.body.classList.toggle("focus-page-shell", active === "focus");
    document.documentElement.setAttribute("data-theme", theme);
    document.title = `${pageTitle} · V-SPACE AI`;
    save("lifeos-theme", theme);
    return () => { document.body.classList.remove("app-body", "studio-theme", "focus-page-shell", "focus-immersive-active", "focus-panel-open", "focus-review-open"); };
  }, [theme, active, pageTitle]);
  useEffect(() => { save("vspace-sidebar-collapsed", String(collapsed)); }, [collapsed]);
  useEffect(() => {
    function keydown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setCommand(value => value ? null : "search"); }
      if (event.key === "Escape") { setProfileOpen(false); setMobileOpen(false); }
    }
    function outside(event: PointerEvent) { if (!profileRef.current?.contains(event.target as Node)) setProfileOpen(false); }
    document.addEventListener("keydown", keydown);
    document.addEventListener("pointerdown", outside);
    return () => { document.removeEventListener("keydown", keydown); document.removeEventListener("pointerdown", outside); };
  }, []);
  useEffect(() => {
    if (!mobileOpen) return;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    sidebarRef.current?.querySelector<HTMLElement>("a, button")?.focus();
    function trap(event: KeyboardEvent) {
      if (event.key !== "Tab") return;
      const elements = Array.from(sidebarRef.current?.querySelectorAll<HTMLElement>("a,button") || []).filter(el => el.offsetParent !== null);
      const first = elements[0], last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    document.addEventListener("keydown", trap);
    return () => { document.body.style.overflow = overflow; document.removeEventListener("keydown", trap); mobileButtonRef.current?.focus(); };
  }, [mobileOpen]);

  async function handleLogout() {
    if (!window.confirm("Log out of V-SPACE AI?")) return;
    setLoggingOut(true); setLogoutError(null);
    try { await logout(); navigate("/login", true); }
    catch { setLogoutError("We couldn’t log you out. Please try again."); }
    finally { setLoggingOut(false); }
  }
  function nav(item: NavItem) {
    return <a key={item.key} href={item.href} title={item.label} aria-current={active === item.key ? "page" : undefined} className={`navigation-link ${active === item.key ? "active" : ""}`} onClick={() => setMobileOpen(false)}><Icon name={item.icon}/><span>{item.label}</span></a>;
  }
  return <div className={`app-shell vspace-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
    <a href="#workspace-main" className="vs-skip-link">Skip to workspace</a>
    <button type="button" tabIndex={-1} className={`sidebar-overlay ${mobileOpen ? "active" : ""}`} onClick={() => setMobileOpen(false)} aria-label="Close navigation"/>
    <aside ref={sidebarRef} id="workspace-navigation" aria-label="Workspace navigation" className={`app-sidebar ${mobileOpen ? "mobile-open" : ""}`}>
      <div className="sidebar-header"><a href="/dashboard" className="app-brand" aria-label="V-SPACE AI dashboard"><span className="app-brand-mark"><BrandMark/></span><span className="app-brand-copy"><strong>V-SPACE <em>AI</em></strong><small>Virtual Smart Space</small></span></a><button type="button" className="sidebar-close-button" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><Icon name="close"/></button></div>
      <nav className="app-navigation" aria-label="Main navigation">{groups.map(group => <div className="vs-nav-group" key={group.label}><span className="navigation-label">{group.label}</span>{group.items.filter(item => item.key !== "modules" || experience.ui.modules_visible).map(item => nav(item.key === "modules" ? { ...item, label: experience.ui.module_label } : item))}</div>)}</nav>
      <div className="vs-sidebar-footer"><div className="vs-control-note"><Icon name="shield"/><div><strong>You’re in control</strong><span>Review AI changes before they’re applied.</span></div></div>{nav({ key: "settings", href: "/settings", label: "Settings", icon: "settings" })}<a href="/settings" className="sidebar-user-summary" title={user.name}><span className="account-avatar">{initial}</span><span className="account-information"><strong>{user.name}</strong><span>{experience.ui.workspace_label}</span></span><Icon name="chevron"/></a></div>
    </aside>
    <div className="app-main">
      <header className="app-topbar"><div className="topbar-left"><button ref={mobileButtonRef} type="button" className="mobile-menu-button vs-icon-button" onClick={() => setMobileOpen(true)} aria-label="Open navigation" aria-expanded={mobileOpen} aria-controls="workspace-navigation"><Icon name="menu"/></button><button type="button" className="vs-collapse-button vs-icon-button" onClick={() => setCollapsed(v => !v)} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}><Icon name="collapse"/></button><div className="topbar-context"><span>Workspace</span><span aria-hidden="true">/</span><strong>{pageTitle}</strong></div></div>
        <div className="topbar-actions"><button type="button" className="workspace-search-button" onClick={() => setCommand("search")}><Icon name="search"/><span>Search workspace</span><kbd>Ctrl K</kbd></button><button type="button" className="vs-quick-create" onClick={() => setCommand("create")}><Icon name="plus"/><span>Create</span></button><button type="button" className="vs-icon-button" onClick={() => setTheme(v => v === "dark" ? "light" : "dark")} aria-label="Toggle theme" title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}><Icon name={theme === "dark" ? "sun" : "moon"}/></button><a className="vs-icon-button notification-button lifeos-proactive-bell" href="/notifications/history" aria-label="Notifications" title="Notifications"><Icon name="bell"/>{unread > 0 ? <span className="lifeos-proactive-badge">{unread > 99 ? "99+" : unread}</span> : null}</a>
          <div className="profile-menu-wrapper" ref={profileRef}><button type="button" className="vs-profile-trigger" aria-label="Account menu" aria-expanded={profileOpen} onClick={() => setProfileOpen(v => !v)}><span className="topbar-avatar">{initial}</span></button>{profileOpen ? <div className="profile-dropdown open"><div className="profile-dropdown-header"><strong>{user.name}</strong><span>{user.email}</span></div><a className="profile-dropdown-item" href="/settings">Personalization & experience</a><a className="profile-dropdown-item" href="/notifications/settings">Notification preferences</a><button type="button" className="profile-logout-button" onClick={() => void handleLogout()} disabled={loggingOut}>{loggingOut ? "Logging out…" : "Log out"}</button>{logoutError ? <p role="alert">{logoutError}</p> : null}</div> : null}</div>
        </div>
      </header>
      <main className="app-content" id="workspace-main" tabIndex={-1}><FrontendErrorBoundary>{children}</FrontendErrorBoundary></main>
    </div>
    {command ? <CommandPalette key={command} onClose={() => setCommand(null)} createOnly={command === "create"} modulesVisible={experience.ui.modules_visible} moduleLabel={experience.ui.module_label}/> : null}
  </div>;
}
