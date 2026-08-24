import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { PublicOnly } from "./auth/PublicOnly";
import { RequireAuth } from "./auth/RequireAuth";
import { DashboardPage } from "./pages/DashboardPage";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";
import { MigrationPage } from "./pages/MigrationPage";
import { RegisterPage } from "./pages/RegisterPage";

const router = createBrowserRouter([
  { path: "/", element: <LandingPage /> },
  {
    path: "/login",
    element: <PublicOnly><LoginPage /></PublicOnly>,
  },
  {
    path: "/register",
    element: <PublicOnly><RegisterPage /></PublicOnly>,
  },
  {
    element: <RequireAuth><AppShell /></RequireAuth>,
    children: [
      { path: "dashboard", element: <DashboardPage /> },
      {
        path: "projects",
        element: <MigrationPage title="Projects" description="Projects are next in the React migration. The current Flask project workflows remain untouched until the API contract is complete." />,
      },
      {
        path: "tasks",
        element: <MigrationPage title="Tasks" description="Task management is still served by the proven backend UI while we expose the existing task service through API v1." />,
      },
      {
        path: "notes",
        element: <MigrationPage title="Notes" description="Notes and project-aware AI analysis remain on the existing backend until their typed React contract is ready." />,
      },
      {
        path: "documents",
        element: <MigrationPage title="Document Brain" description="Document Brain stays on the proven backend during Phase 1 so RAG, citations, comparison and versioning are not destabilized." />,
      },
      {
        path: "modules",
        element: <MigrationPage title="Modules & Lectures" description="Modules are future functionality and will be built on the new architecture after the existing application reaches React parity." />,
      },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);

export function App() {
  return <RouterProvider router={router} />;
}
