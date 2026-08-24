import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { User } from "../api/types";
import { logout } from "../auth/session";
import { navigate } from "../core/navigation";

export type NativeSection =
  | "dashboard" | "projects" | "tasks" | "notes" | "focus"
  | "analytics" | "notifications" | "documents";

const navItems: Array<{ key: NativeSection; href: string; label: string; icon: string }> = [
  { key: "dashboard", href: "/dashboard", label: "Dashboard", icon: "D" },
  { key: "projects", href: "/projects", label: "Projects", icon: "P" },
  { key: "tasks", href: "/tasks", label: "Tasks", icon: "T" },
  { key: "notes", href: "/notes", label: "Notes", icon: "N" },
  { key: "focus", href: "/focus", label: "Focus", icon: "F" },
  { key: "analytics", href: "/analytics", label: "Analytics", icon: "A" },
  { key: "documents", href: "/documents", label: "Document Brain", icon: "DB" },
  { key: "notifications", href: "/notifications/settings", label: "Notifications", icon: "!" },
];

export function NativeWorkspaceShell({ user, active, children }: { user: User; active: NativeSection; children: ReactNode }) {
  const [profileOpen, setProfileOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    const saved = localStorage.getItem("lifeos-theme");
    return saved === "light" ? "light" : "dark";
  });
  const [loggingOut, setLoggingOut] = useState(false);
  const initial = (user.name || user.email || "L").trim().slice(0, 1).toUpperCase();
  const firstName = useMemo(() => (user.name || "Workspace").trim().split(/\s+/)[0], [user.name]);

  useEffect(() => {
    document.body.className = `app-body studio-theme ${theme === "light" ? "light-theme" : ""}`.trim();
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("lifeos-theme", theme);
  }, [theme]);

  async function handleLogout() {
    if (!window.confirm("Log out of LifeOS?")) return;
    setLoggingOut(true);
    try {
      await logout();
      navigate("/login", true);
    } finally {
      setLoggingOut(false);
    }
  }

  return (
    <div className="app-shell-root">
      <aside className={`app-sidebar ${mobileOpen ? "mobile-open" : ""}`}>
        <div>
          <a href="/dashboard" className="sidebar-brand-row">
            <span className="brand-mark small">L</span>
            <span><strong className="brand">LifeOS AI</strong><small className="brand-subtitle">Private workspace</small></span>
          </a>
          <nav className="native-nav" aria-label="Workspace navigation">
            {navItems.map((item) => (
              <a key={item.key} href={item.href} className={`navigation-link ${active === item.key ? "active" : ""}`}>
                <span className="nav-icon">{item.icon}</span><span>{item.label}</span>
              </a>
            ))}
          </nav>
        </div>
        <div className="sidebar-bottom">
          <div className="migration-badge"><strong>React frontend</strong><span>UI fully separated from Flask rendering.</span></div>
          <div className="sidebar-user-summary"><div className="account-avatar">{initial}</div><div className="account-information"><strong>{user.name}</strong><span>{user.email}</span></div></div>
        </div>
      </aside>

      <div className="app-main">
        <header className="app-topbar">
          <div className="topbar-left">
            <button type="button" className="mobile-menu-button" onClick={() => setMobileOpen((value) => !value)} aria-label="Toggle navigation"><span /><span /><span /></button>
            <div className="topbar-context"><span>Private workspace</span><strong>LifeOS AI</strong></div>
          </div>
          <div className="topbar-actions">
            <a className="icon-action-button notification-button" href="/notifications/history" title="Notification history" aria-label="Notification history">!</a>
            <button type="button" className="theme-switch" onClick={() => setTheme((value) => value === "dark" ? "light" : "dark")} aria-label="Toggle theme" title="Toggle theme">
              <span aria-hidden="true">{theme === "dark" ? "☾" : "☀"}</span>
            </button>
            <div className="profile-menu-wrapper">
              <button type="button" className="profile-menu-button" onClick={() => setProfileOpen((value) => !value)} aria-expanded={profileOpen}>
                <span className="topbar-avatar">{initial}</span><span className="topbar-user-copy"><strong>{firstName}</strong><small>Workspace owner</small></span><span>⌄</span>
              </button>
              {profileOpen ? (
                <div className="profile-dropdown is-open">
                  <div className="profile-dropdown-header"><strong>{user.name}</strong><span>{user.email}</span></div>
                  <a className="profile-dropdown-item" href="/notifications/settings">Notification settings</a>
                  <button type="button" className="profile-logout-button" disabled={loggingOut} onClick={handleLogout}>{loggingOut ? "Logging out…" : "Log out"}</button>
                </div>
              ) : null}
            </div>
          </div>
        </header>
        <main className="app-content">{children}</main>
      </div>
    </div>
  );
}
