import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useSession } from "./session";

export function PublicOnly({ children }: { children: ReactNode }) {
  const session = useSession();

  if (session.isPending) {
    return (
      <div className="screen-state">
        <div className="spinner" />
        <strong>Loading LifeOS</strong>
      </div>
    );
  }

  if (session.data?.authenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
}
