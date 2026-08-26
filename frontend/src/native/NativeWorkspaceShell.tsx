import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { User } from "../api/types";
import { FrontendErrorBoundary } from "../components/FrontendErrorBoundary";
import { logout } from "../auth/session";
import { navigate } from "../core/navigation";

export type NativeSection =
  | "dashboard" | "projects" | "tasks" | "notes" | "focus"
  | "analytics" | "notifications" | "documents";

type NavItem = { key: NativeSection; href: string; label: string; small?: string; path: string };
const workspaceItems: NavItem[] = [
  { key: "dashboard", href: "/dashboard", label: "Dashboard", path: "M3 13h8V3H3v10Zm0 8h8v-6H3v6Zm10 0h8V11h-8v10Zm0-18v6h8V3h-8Z" },
  { key: "projects", href: "/projects", label: "Projects", path: "M3 6.5A2.5 2.5 0 0 1 5.5 4H9l2 2h7.5A2.5 2.5 0 0 1 21 8.5v8A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5v-10Z" },
  { key: "tasks", href: "/tasks", label: "Tasks", small: "All projects", path: "M9 5h11v2H9V5Zm0 6h11v2H9v-2Zm0 6h11v2H9v-2ZM4.5 4A1.5 1.5 0 1 1 3 5.5 1.5 1.5 0 0 1 4.5 4Zm0 6A1.5 1.5 0 1 1 3 11.5 1.5 1.5 0 0 1 4.5 10Zm0 6A1.5 1.5 0 1 1 3 17.5 1.5 1.5 0 0 1 4.5 16Z" },
  { key: "focus", href: "/focus", label: "Focus Mode", small: "Deep work", path: "M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Zm1 11h4v-2h-3V6h-2v7h1Z" },
  { key: "analytics", href: "/analytics", label: "Analytics", small: "Trends & reports", path: "M4 19h16v2H2V3h2v16Zm3-3h3V9H7v7Zm5 0h3V5h-3v11Zm5 0h3v-4h-3v4Z" },
  { key: "notifications", href: "/notifications/settings", label: "Notifications", path: "M12 22a2.8 2.8 0 0 0 2.7-2h-5.4A2.8 2.8 0 0 0 12 22Zm8-6h-1V11a7 7 0 0 0-5-6.7V3a2 2 0 0 0-4 0v1.3A7 7 0 0 0 5 11v5H4a1 1 0 0 0 0 2h16a1 1 0 0 0 0-2Z" },
];
const intelligenceItems: NavItem[] = [
  { key: "notes", href: "/notes", label: "AI Notes", small: "Knowledge", path: "M4 4h16v12H7l-3 3V4Zm4 4v2h8V8H8Zm0 4v2h5v-2H8Z" },
  { key: "documents", href: "/documents", label: "Document Brain", small: "Grounded AI", path: "M6 2h8l4 4v16H6V2Zm8 1.5V7h3.5L14 3.5ZM9 11v2h6v-2H9Zm0 4v2h6v-2H9Z" },
];

const context: Record<NativeSection, { kicker: string; title: string }> = {
  dashboard: { kicker: "Execution overview", title: "Dashboard" },
  projects: { kicker: "Project workspace", title: "Projects" },
  tasks: { kicker: "Execution center", title: "Tasks" },
  notes: { kicker: "Knowledge workspace", title: "AI Notes" },
  focus: { kicker: "Deep work", title: "Focus Mode" },
  analytics: { kicker: "Performance intelligence", title: "Analytics" },
  notifications: { kicker: "Smart notifications", title: "Notifications" },
  documents: { kicker: "Grounded intelligence", title: "Document Brain" },
};

function NavLink({ item, active }: { item: NavItem; active: NativeSection }) {
  return <a href={item.href} className={`navigation-link ${active === item.key ? "active" : ""}`}>
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d={item.path}/></svg>
    <span>{item.label}</span>{item.small ? <small>{item.small}</small> : null}
  </a>;
}

export function NativeWorkspaceShell({ user, active, children }: { user: User; active: NativeSection; children: ReactNode }) {
  const [profileOpen, setProfileOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">(() => localStorage.getItem("lifeos-theme") === "light" ? "light" : "dark");
  const [loggingOut, setLoggingOut] = useState(false);
  const initial = (user.name || user.email || "L").trim().slice(0, 1).toUpperCase();
  const firstName = useMemo(() => (user.name || "Workspace").trim().split(/\s+/)[0], [user.name]);
  const pageContext = context[active];

  useEffect(() => {
    document.body.classList.add("app-body", "studio-theme");
    document.body.classList.toggle("focus-page-shell", active === "focus");
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("lifeos-theme", theme);

    return () => {
      if (active === "focus") {
        document.body.classList.remove("focus-page-shell", "focus-immersive-active", "focus-panel-open", "focus-review-open");
      }
    };
  }, [theme, active]);

  async function handleLogout() {
    if (!window.confirm("Log out of LifeOS?")) return;
    setLoggingOut(true);
    try { await logout(); navigate("/login", true); }
    finally { setLoggingOut(false); }
  }

  return <div className="app-shell">
    <button type="button" className={`sidebar-overlay ${mobileOpen ? "active" : ""}`} onClick={() => setMobileOpen(false)} aria-label="Close navigation" />
    <aside className={`app-sidebar ${mobileOpen ? "mobile-open" : ""}`}>
      <div className="sidebar-header">
        <a href="/dashboard" className="app-brand">
          <span className="app-brand-mark">L</span>
          <span className="app-brand-copy"><strong>LifeOS AI</strong><small>Personal workspace</small></span>
        </a>
        <button type="button" className="sidebar-close-button" onClick={() => setMobileOpen(false)} aria-label="Close navigation">×</button>
      </div>
      <nav className="app-navigation" aria-label="Main navigation">
        <span className="navigation-label">Workspace</span>
        {workspaceItems.map((item) => <NavLink item={item} active={active} key={item.key}/>) }
        <span className="navigation-label navigation-label-spaced">Intelligence</span>
        {intelligenceItems.map((item) => <NavLink item={item} active={active} key={item.key}/>) }
        <span className="navigation-label navigation-label-spaced">Planning</span>
        <span className="navigation-link navigation-link-disabled"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 2 2.4 5.1L20 8l-4 4 .9 5.7L12 15l-4.9 2.7L8 12 4 8l5.6-.9L12 2Z"/></svg><span>Smart Plan</span><em>Soon</em></span>
      </nav>
      <div className="sidebar-system-card"><div className="system-card-heading"><span className="system-status-dot"/><strong>All systems ready</strong></div><p>Your workspace is connected and ready.</p></div>
      <div className="sidebar-user-summary"><div className="account-avatar">{initial}</div><div className="account-information"><strong>{user.name}</strong><span>{user.email}</span></div></div>
    </aside>

    <div className="app-main">
      <header className="app-topbar">
        <div className="topbar-left">
          <button type="button" className="mobile-menu-button" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><span/><span/><span/></button>
          <div className="topbar-context"><span>{pageContext.kicker}</span><strong>{pageContext.title}</strong></div>
        </div>
        <div className="topbar-actions">
          <button type="button" className="workspace-search-button" title="Global search will be connected in a later phase"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m21 20-5.2-5.2a7 7 0 1 0-1.4 1.4L20 21l1-1ZM5 10a5 5 0 1 1 10 0 5 5 0 0 1-10 0Z"/></svg><span>Search workspace</span><kbd>Ctrl K</kbd></button>
          <button type="button" className="theme-switch" onClick={() => setTheme((v) => v === "dark" ? "light" : "dark")} aria-label="Toggle theme" title="Toggle theme">
            <span className="theme-switch-icon theme-switch-sun" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 4V2m0 20v-2M4 12H2m20 0h-2M5.64 5.64 4.22 4.22m15.56 15.56-1.42-1.42M18.36 5.64l1.42-1.42M4.22 19.78l1.42-1.42M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z"/></svg></span>
            <span className="theme-switch-track" aria-hidden="true"><span className="theme-switch-thumb"/></span>
            <span className="theme-switch-icon theme-switch-moon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M20.3 15.2A8 8 0 0 1 8.8 3.7 8.5 8.5 0 1 0 20.3 15.2Z"/></svg></span>
          </button>
          <a className="icon-action-button notification-button" href="/notifications/history" title="Notifications" aria-label="Notifications"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 22a2.4 2.4 0 0 0 2.3-2h-4.6A2.4 2.4 0 0 0 12 22Zm7-5-2-2v-4.5a5 5 0 0 0-4-4.9V4a1 1 0 0 0-2 0v1.6a5 5 0 0 0-4 4.9V15l-2 2v1h14v-1Z"/></svg></a>
          <div className="profile-menu-wrapper">
            <button type="button" className="profile-menu-button" onClick={() => setProfileOpen(v => !v)} aria-expanded={profileOpen}><span className="topbar-avatar">{initial}</span><span className="topbar-user-copy"><strong>{firstName}</strong><small>Workspace owner</small></span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 10 5 5 5-5H7Z"/></svg></button>
            <div className={`profile-dropdown ${profileOpen ? "open" : ""}`}><div className="profile-dropdown-header"><strong>{user.name}</strong><span>{user.email}</span></div><span className="profile-dropdown-item profile-dropdown-disabled">Profile settings<small>Phase 4</small></span><button type="button" className="profile-logout-button" onClick={handleLogout} disabled={loggingOut}>{loggingOut ? "Logging out…" : "Log out"}</button></div>
          </div>
        </div>
      </header>
      <main className="app-content"><FrontendErrorBoundary>{children}</FrontendErrorBoundary></main>
    </div>
  </div>;
}
