import { LegacyScreen } from "./legacy/LegacyScreen";
import { ProjectsPage } from "./pages/ProjectsPage";

export function App() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";

  // First native React parity slice. Every other URL still uses the proven
  // compatibility renderer until its own screen passes parity checks.
  if (path === "/projects") {
    return <ProjectsPage />;
  }

  return <LegacyScreen />;
}
