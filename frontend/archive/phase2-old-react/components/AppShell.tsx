import { useMutation, useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { logout, sessionQueryKey, useSession } from "../auth/session";

const links = [
  ["/dashboard", "Dashboard", "▦"],
  ["/projects", "Projects", "P"],
  ["/tasks", "Tasks", "✓"],
  ["/notes", "Notes", "N"],
  ["/documents", "Document Brain", "D"],
  ["/modules", "Modules", "M"],
] as const;

export function AppShell() {
  const session = useSession();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess: (nextSession) => {
      queryClient.setQueryData(sessionQueryKey, nextSession);
      queryClient.clear();
      navigate("/login", { replace: true });
    },
  });

  const user = session.data?.user;
  const initials = user?.name
    ? user.name
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0]?.toUpperCase())
        .join("")
    : "L";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-top">
          <div className="sidebar-brand-row">
            <span className="brand-mark small">L</span>
            <div>
              <div className="brand">LifeOS AI</div>
              <div className="brand-subtitle">Execution Intelligence</div>
            </div>
          </div>

          <nav aria-label="Main navigation">
            {links.map(([to, label, icon]) => (
              <NavLink key={to} to={to}>
                <span className="nav-icon">{icon}</span>
                <span>{label}</span>
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="sidebar-bottom">
          <div className="migration-badge">
            <strong>React migration</strong>
            <span>Phase 2 · Projects + Tasks</span>
          </div>

          <div className="user-card">
            <span className="user-avatar">{initials}</span>
            <div className="user-meta">
              <strong>{user?.name ?? "LifeOS user"}</strong>
              <span>{user?.email ?? ""}</span>
            </div>
            <button
              type="button"
              className="icon-button"
              onClick={() => logoutMutation.mutate()}
              disabled={logoutMutation.isPending}
              title="Log out"
              aria-label="Log out"
            >
              ↗
            </button>
          </div>
        </div>
      </aside>

      <div className="workspace-shell">
        <header className="topbar">
          <div>
            <span className="topbar-label">LifeOS Workspace</span>
          </div>
          <div className="topbar-actions">
            <span className="api-status"><i /> API connected</span>
          </div>
        </header>
        <main className="content"><Outlet /></main>
      </div>
    </div>
  );
}
