import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../api/client";

type Meta = {
  name: string;
  architecture: string;
  api_version: string;
  preferred_database: string;
  legacy_web_enabled: boolean;
  frontend_migration: string;
};

export function OverviewPage() {
  const meta = useQuery({
    queryKey: ["meta"],
    queryFn: () => apiGet<Meta>("/api/v1/meta"),
  });

  return (
    <section>
      <span className="eyebrow">Architecture migration</span>
      <h1>LifeOS Foundation V2</h1>
      <p className="lead">
        Stable Flask domain backend, versioned API, PostgreSQL/Neon-ready data
        layer, and a React + TypeScript frontend migration path.
      </p>

      <div className="cards">
        <article><strong>Backend</strong><span>Flask modular monolith</span></article>
        <article><strong>Database</strong><span>{meta.data?.preferred_database ?? "PostgreSQL"}</span></article>
        <article><strong>API</strong><span>{meta.data?.api_version ?? "v1"}</span></article>
        <article><strong>Frontend</strong><span>React migration shell</span></article>
      </div>

      <div className="notice">
        <strong>Safe migration rule</strong>
        <p>
          Existing user workflows are not deleted. Each React screen replaces a
          legacy screen only after its API contract and regression tests pass.
        </p>
      </div>
    </section>
  );
}
