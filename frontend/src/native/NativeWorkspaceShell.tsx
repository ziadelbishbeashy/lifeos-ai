import type { FormEvent, ReactNode } from "react";
import { logout } from "../auth/session";
import type { User } from "../api/types";

type Props = {
  user: User;
  active: "projects";
  children: ReactNode;
};

const navLinks = [
  { href: "/dashboard", label: "Dashboard", path: "M3 13h8V3H3v10Zm0 8h8v-6H3v6Zm10 0h8V11h-8v10Zm0-18v6h8V3h-8Z", loadingTitle: "Opening dashboard", loadingMessage: "Loading your workspace overview..." },
  { href: "/projects", label: "Projects", path: "M3 6.5A2.5 2.5 0 0 1 5.5 4H9l2 2h7.5A2.5 2.5 0 0 1 21 8.5v8A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5v-10Z", loadingTitle: "Opening projects", loadingMessage: "Loading your project workspace..." },
  { href: "/tasks", label: "Tasks", small: "All projects", path: "M9 5h11v2H9V5Zm0 6h11v2H9v-2Zm0 6h11v2H9v-2ZM4.5 4A1.5 1.5 0 1 1 3 5.5 1.5 1.5 0 0 1 4.5 4Zm0 6A1.5 1.5 0 1 1 3 11.5 1.5 1.5 0 0 1 4.5 10Zm0 6A1.5 1.5 0 1 1 3 17.5 1.5 1.5 0 0 1 4.5 16Z", loadingTitle: "Opening tasks", loadingMessage: "Loading all workspace tasks..." },
  { href: "/focus/", label: "Focus Mode", small: "Deep work", path: "M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Zm1 11h4v-2h-3V6h-2v7h1Z", loadingTitle: "Opening focus mode", loadingMessage: "Preparing your deep-work workspace..." },
  { href: "/analytics/", label: "Analytics", small: "Trends & reports", path: "M4 19h16v2H2V3h2v16Zm3-3h3V9H7v7Zm5 0h3V5h-3v11Zm5 0h3v-4h-3v4Z", loadingTitle: "Opening analytics", loadingMessage: "Calculating your workspace performance..." },
  { href: "/notifications/settings", label: "Notifications", small: "Phase 5.1", path: "M12 22a2.8 2.8 0 0 0 2.7-2h-5.4A2.8 2.8 0 0 0 12 22Zm8-6h-1V11a7 7 0 0 0-5-6.7V3a2 2 0 0 0-4 0v1.3A7 7 0 0 0 5 11v5H4a1 1 0 0 0 0 2h16a1 1 0 0 0 0-2Z", loadingTitle: "Opening notifications", loadingMessage: "Loading notification preferences..." },
] as const;

async function handleLogout(event: FormEvent<HTMLFormElement>) {
  const form = event.currentTarget;
  if (form.dataset.confirmApproved !== "true") return;
  event.preventDefault();
  delete form.dataset.confirmApproved;
  try {
    (window as any).lifeOSLoading?.show?.({ title: "Logging out", message: "Ending your LifeOS session safely..." });
    await logout();
    window.location.replace("/login");
  } catch (error) {
    console.error(error);
    (window as any).lifeOSLoading?.hide?.();
    window.alert("LifeOS could not log out. Please try again.");
  }
}

function NavIcon({ path }: { path: string }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={path} /></svg>;
}

export function NativeWorkspaceShell({ user, active, children }: Props) {
  const firstName = user.name.split(/\s+/).filter(Boolean)[0] || user.name;
  const initial = user.name.trim().charAt(0).toUpperCase() || "L";

  return (
    <div className="app-shell">
      <button type="button" className="sidebar-overlay" id="sidebarOverlay" aria-label="Close navigation" />

      <aside className="app-sidebar" id="appSidebar">
        <div className="sidebar-header">
          <a href="/dashboard" className="app-brand" data-page-loading data-loading-title="Opening dashboard" data-loading-message="Loading your workspace overview...">
            <span className="app-brand-mark">L</span>
            <span className="app-brand-copy"><strong>LifeOS AI</strong><small>Focus Studio</small></span>
          </a>
          <button type="button" className="sidebar-close-button" id="sidebarCloseButton" aria-label="Close navigation">×</button>
        </div>

        <nav className="app-navigation" aria-label="Main navigation">
          <span className="navigation-label">Workspace</span>
          {navLinks.map((item) => (
            <a key={item.href} href={item.href} className={`navigation-link${active === "projects" && item.href === "/projects" ? " active" : ""}`} data-page-loading data-loading-title={item.loadingTitle} data-loading-message={item.loadingMessage}>
              <NavIcon path={item.path} />
              <span>{item.label}</span>
              {"small" in item && item.small ? <small>{item.small}</small> : null}
            </a>
          ))}

          <span className="navigation-label navigation-label-spaced">Intelligence</span>
          <a href="/notes/" className="navigation-link" data-page-loading data-loading-title="Opening AI Notes" data-loading-message="Loading your notes workspace...">
            <NavIcon path="M4 4h16v12H7l-3 3V4Zm4 4v2h8V8H8Zm0 4v2h5v-2H8Z" /><span>AI Notes</span><small>Phase 6.1</small>
          </a>
          <a href="/documents/" className="navigation-link" data-page-loading data-loading-title="Opening Document Brain" data-loading-message="Loading your project documents...">
            <NavIcon path="M6 2h9l5 5v15H6V2Zm8 2v4h4l-4-4ZM9 12h8v-2H9v2Zm0 4h8v-2H9v2Zm0 4h6v-2H9v2Z" /><span>Document Brain</span><small>Phase 6.2</small>
          </a>
          <span className="navigation-link navigation-link-disabled"><NavIcon path="m12 2 2.4 5.1L20 8l-4 4 .9 5.7L12 15l-4.9 2.7L8 12 4 8l5.6-.9L12 2Z" /><span>Smart Plan</span><em>Soon</em></span>
        </nav>

        <div className="sidebar-system-card"><div className="system-card-heading"><span className="system-status-dot" /><strong>Workspace online</strong></div><p>Projects and task management are active.</p></div>
        <div className="sidebar-user-summary"><div className="account-avatar">{initial}</div><div className="account-information"><strong>{user.name}</strong><span>{user.email}</span></div></div>
      </aside>

      <div className="app-main">
        <header className="app-topbar">
          <div className="topbar-left">
            <button type="button" className="mobile-menu-button" id="mobileMenuButton" aria-label="Open navigation"><span /><span /><span /></button>
            <div className="topbar-context"><span>Private workspace</span><strong>LifeOS AI</strong></div>
          </div>

          <div className="topbar-actions">
            <button type="button" className="workspace-search-button" title="Global search will be connected in a later phase">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m21 20-5.2-5.2a7 7 0 1 0-1.4 1.4L20 21l1-1ZM5 10a5 5 0 1 1 10 0 5 5 0 0 1-10 0Z" /></svg><span>Search workspace</span><kbd>Ctrl K</kbd>
            </button>

            <button type="button" className="theme-switch" id="themeToggleButton" aria-label="Switch to light mode" aria-pressed="false" title="Switch to light mode">
              <span className="theme-switch-icon theme-switch-sun" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 4V2m0 20v-2M4 12H2m20 0h-2M5.64 5.64 4.22 4.22m15.56 15.56-1.42-1.42M18.36 5.64l1.42-1.42M4.22 19.78l1.42-1.42M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z" /></svg></span>
              <span className="theme-switch-track" aria-hidden="true"><span className="theme-switch-thumb"><svg className="theme-switch-thumb-icon" id="themeToggleIcon" viewBox="0 0 24 24"><path d="M20.3 15.2A8 8 0 0 1 8.8 3.7 8.5 8.5 0 1 0 20.3 15.2Z" /></svg></span></span>
              <span className="theme-switch-icon theme-switch-moon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M20.3 15.2A8 8 0 0 1 8.8 3.7 8.5 8.5 0 1 0 20.3 15.2Z" /></svg></span>
              <span className="sr-only" id="themeToggleLabel">Dark mode</span>
            </button>

            <div className="notification-center-wrapper" id="notificationCenterWrapper">
              <button type="button" className="icon-action-button notification-button" id="notificationButton" aria-label="Open notifications" aria-expanded="false" aria-controls="notificationPanel" title="Notifications">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 22a2.4 2.4 0 0 0 2.3-2h-4.6A2.4 2.4 0 0 0 12 22Zm7-5-2-2v-4.5a5 5 0 0 0-4-4.9V4a1 1 0 0 0-2 0v1.6a5 5 0 0 0-4 4.9V15l-2 2v1h14v-1Z" /></svg><span className="notification-badge" id="notificationBadge" hidden>0</span>
              </button>
              <section className="notification-panel" id="notificationPanel" aria-hidden="true" aria-label="Notification center">
                <header className="notification-panel-header"><div><span className="notification-panel-kicker">LifeOS activity</span><h2>Notifications</h2></div><button type="button" className="notification-panel-close" id="notificationPanelClose" aria-label="Close notifications">×</button></header>
                <div className="notification-panel-summary"><span id="notificationSummary">You are all caught up</span><button type="button" className="notification-text-action" id="markAllNotificationsRead">Mark all read</button></div>
                <div className="notification-filter-tabs" role="tablist" aria-label="Notification filters">
                  <button type="button" className="notification-filter-button active" data-notification-filter="all" role="tab" aria-selected="true">All <span id="allNotificationCount">0</span></button>
                  <button type="button" className="notification-filter-button" data-notification-filter="unread" role="tab" aria-selected="false">Unread <span id="unreadNotificationCount">0</span></button>
                </div>
                <div className="notification-list" id="notificationList" aria-live="polite" />
                <div className="notification-empty-state" id="notificationEmptyState" hidden><span className="notification-empty-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 22a2.4 2.4 0 0 0 2.3-2h-4.6A2.4 2.4 0 0 0 12 22Zm7-5-2-2v-4.5a5 5 0 0 0-4-4.9V4a1 1 0 0 0-2 0v1.6a5 5 0 0 0-4 4.9V15l-2 2v1h14v-1Z" /></svg></span><strong>No notifications here</strong><p>New activity and future deadline reminders will appear in this panel.</p></div>
                <footer className="notification-panel-footer"><button type="button" className="notification-footer-button" id="clearReadNotifications">Clear read</button><span>Deadline intelligence coming next</span></footer>
              </section>
            </div>

            <div className="profile-menu-wrapper">
              <button type="button" className="profile-menu-button" id="profileMenuButton" aria-expanded="false" aria-controls="profileDropdown"><span className="topbar-avatar">{initial}</span><span className="topbar-user-copy"><strong>{firstName}</strong><small>Workspace owner</small></span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 10 5 5 5-5H7Z" /></svg></button>
              <div className="profile-dropdown" id="profileDropdown">
                <div className="profile-dropdown-header"><strong>{user.name}</strong><span>{user.email}</span></div>
                <span className="profile-dropdown-item profile-dropdown-disabled">Profile settings <small>Phase 4</small></span>
                <form method="POST" action="/api/v1/auth/logout" data-confirm data-confirm-title="Log out?" data-confirm-message="You will be returned to the login page." data-confirm-text="Log out" data-confirm-cancel="Stay here" data-confirm-variant="default" data-confirm-icon="?" data-loading-title="Logging out" data-loading-message="Ending your LifeOS session safely..." onSubmit={handleLogout}>
                  <button type="submit" className="profile-logout-button">Log out</button>
                </form>
              </div>
            </div>
          </div>
        </header>

        <main className="app-content">{children}</main>
      </div>

      <div className="confirmation-modal-backdrop" id="confirmationModalBackdrop" hidden><section className="confirmation-modal" id="confirmationModal" role="dialog" aria-modal="true" aria-labelledby="confirmationModalTitle" aria-describedby="confirmationModalMessage"><div className="confirmation-modal-icon" id="confirmationModalIcon">!</div><div className="confirmation-modal-content"><span className="confirmation-modal-kicker">Confirmation required</span><h2 id="confirmationModalTitle">Are you sure?</h2><p id="confirmationModalMessage">This action needs your confirmation before continuing.</p></div><div className="confirmation-modal-actions"><button type="button" className="confirmation-cancel-button" id="confirmationCancelButton">Cancel</button><button type="button" className="confirmation-confirm-button" id="confirmationConfirmButton">Confirm</button></div></section></div>
      <div className="global-loading-overlay" id="globalLoadingOverlay" aria-hidden="true"><div className="global-loading-card"><div className="global-loading-logo">L</div><div className="global-loading-copy"><strong id="globalLoadingTitle">Preparing workspace</strong><span id="globalLoadingMessage">LifeOS AI is processing your request...</span></div><div className="global-loading-bar"><span /></div></div></div>
    </div>
  );
}
