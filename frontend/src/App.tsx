import type { ReactNode } from "react";
import { useSession } from "./auth/session";
import { PageState } from "./components/NativeUi";
import { navigate } from "./core/navigation";
import { NativeWorkspaceShell, type NativeSection } from "./native/NativeWorkspaceShell";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DocumentComparePage, DocumentComparisonDetailsPage } from "./pages/DocumentComparePage";
import { DocumentDetailsPage } from "./pages/DocumentDetailsPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { FocusInsightsPage, FocusPage } from "./pages/FocusPage";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";
import { NoteDetailsPage } from "./pages/NoteDetailsPage";
import { NotesPage } from "./pages/NotesPage";
import { NotificationHistoryPage, NotificationSettingsPage } from "./pages/NotificationsPage";
import { ProjectDetailsPage } from "./pages/ProjectDetailsPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { RegisterPage } from "./pages/RegisterPage";
import { TasksPage } from "./pages/TasksPage";

function normalizePath() {
  return window.location.pathname.replace(/\/+$/, "") || "/";
}

function PrivateArea({ active, children }: { active: NativeSection; children: ReactNode }) {
  const session = useSession();

  if (session.isPending) {
    return <PageState title="Opening LifeOS" text="Restoring your private workspace…" />;
  }

  if (session.isError) {
    return <PageState title="Workspace unavailable" text="LifeOS could not verify your session." error retry={() => session.refetch()} />;
  }

  if (!session.data?.authenticated || !session.data.user) {
    const next = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    navigate(`/login?next=${encodeURIComponent(next)}`, true);
    return null;
  }

  return <NativeWorkspaceShell user={session.data.user} active={active}>{children}</NativeWorkspaceShell>;
}

function NotFoundPage() {
  return (
    <section className="workspace-page">
      <PageState title="Page not found" text="This LifeOS screen does not exist." />
      <div className="center-actions"><a className="primary-button" href="/dashboard">Return to dashboard</a></div>
    </section>
  );
}

export function App() {
  const path = normalizePath();

  if (path === "/") return <LandingPage />;
  if (path === "/login") return <LoginPage />;
  if (path === "/register") return <RegisterPage />;

  if (path === "/dashboard") return <PrivateArea active="dashboard"><DashboardPage /></PrivateArea>;
  if (path === "/projects") return <PrivateArea active="projects"><ProjectsPage /></PrivateArea>;
  if (/^\/projects\/\d+$/.test(path)) return <PrivateArea active="projects"><ProjectDetailsPage /></PrivateArea>;
  if (/^\/projects\/\d+\/edit$/.test(path)) {
    navigate(path.replace(/\/edit$/, ""), true);
    return null;
  }

  if (path === "/tasks") return <PrivateArea active="tasks"><TasksPage /></PrivateArea>;
  if (/^\/tasks\/\d+\/edit$/.test(path)) {
    navigate("/tasks", true);
    return null;
  }

  if (path === "/notes") return <PrivateArea active="notes"><NotesPage /></PrivateArea>;
  if (/^\/notes\/\d+$/.test(path)) return <PrivateArea active="notes"><NoteDetailsPage /></PrivateArea>;

  if (path === "/focus") return <PrivateArea active="focus"><FocusPage /></PrivateArea>;
  if (path === "/focus/insights") return <PrivateArea active="focus"><FocusInsightsPage /></PrivateArea>;
  if (path === "/analytics") return <PrivateArea active="analytics"><AnalyticsPage /></PrivateArea>;

  if (path === "/notifications" || path === "/notifications/settings") {
    return <PrivateArea active="notifications"><NotificationSettingsPage /></PrivateArea>;
  }
  if (path === "/notifications/history") return <PrivateArea active="notifications"><NotificationHistoryPage /></PrivateArea>;

  if (path === "/documents" || path === "/documents/dashboard") return <PrivateArea active="documents"><DocumentsPage /></PrivateArea>;
  if (path === "/documents/compare") return <PrivateArea active="documents"><DocumentComparePage /></PrivateArea>;
  if (/^\/documents\/comparisons\/\d+$/.test(path)) return <PrivateArea active="documents"><DocumentComparisonDetailsPage /></PrivateArea>;
  if (/^\/documents\/\d+$/.test(path)) return <PrivateArea active="documents"><DocumentDetailsPage /></PrivateArea>;

  return <PrivateArea active="dashboard"><NotFoundPage /></PrivateArea>;
}
