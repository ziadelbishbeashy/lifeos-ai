import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useSession } from "./session";

export function RequireAuth({ children }: { children: ReactNode }) {
  const session = useSession();
  const location = useLocation();

  if (session.isPending) {
    return (
      <div className="screen-state">
        <div className="spinner" />
        <strong>Opening LifeOS</strong>
        <span>Checking your workspace session…</span>
      </div>
    );
  }

  if (session.isError || !session.data?.authenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
