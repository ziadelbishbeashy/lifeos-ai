import { Link } from "react-router-dom";

export function MigrationPage({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <section className="migration-page">
      <span className="eyebrow">React migration</span>
      <h1>{title}</h1>
      <p className="lead">{description}</p>
      <div className="panel-card migration-panel">
        <strong>Backend functionality is preserved</strong>
        <p>
          This screen has not been moved to React yet. Its existing Flask service
          remains canonical until the matching API contract and React tests are added.
        </p>
        <Link className="secondary-button" to="/dashboard">Back to dashboard</Link>
      </div>
    </section>
  );
}
