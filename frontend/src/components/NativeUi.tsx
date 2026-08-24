import { useState, type ReactNode } from "react";

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description?: string; actions?: ReactNode }) {
  return <header className="workspace-page-header"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1>{description ? <p>{description}</p> : null}</div>{actions ? <div className="header-actions">{actions}</div> : null}</header>;
}

export function PageState({ title, text, error = false, retry }: { title: string; text: string; error?: boolean; retry?: () => void }) {
  return <section className="workspace-page"><div className={`page-state panel-card ${error ? "error-state" : ""}`}>{!error ? <div className="spinner" /> : null}<div><strong>{title}</strong><span>{text}</span></div>{retry ? <button className="secondary-button" onClick={retry}>Try again</button> : null}</div></section>;
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return <article className="native-stat"><span>{label}</span><strong>{value}</strong>{hint ? <small>{hint}</small> : null}</article>;
}

export type Evidence = { page?: number | null; section?: string | null; evidence?: string | null; source_id?: number | string | null } | null | undefined;

export function VerifyButton({ source, label = "Verify" }: { source: Evidence; label?: string }) {
  const [open, setOpen] = useState(false);
  if (!source || (!source.page && !source.section && !source.evidence && !source.source_id)) return null;
  return <div className="verify-control"><button type="button" className="verify-button" onClick={() => setOpen((value) => !value)} title="Verify against document"><span aria-hidden="true">✓</span>{label}</button>{open ? <div className="verify-popover"><div className="verify-popover-head"><strong>Source</strong><button onClick={() => setOpen(false)} aria-label="Close">×</button></div><div className="verify-location">{source.page ? <span>Page {source.page}</span> : null}{source.section ? <span>{source.section}</span> : null}{source.source_id ? <span>Source {source.source_id}</span> : null}</div>{source.evidence ? <blockquote>{source.evidence}</blockquote> : <p>Open the document to inspect the supporting context.</p>}{source.page ? <button className="secondary-button compact" onClick={() => window.dispatchEvent(new CustomEvent("lifeos-open-pdf", { detail: { page: source.page } }))}>Open in PDF</button> : null}</div> : null}</div>;
}

export function EmptyState({ title, text }: { title: string; text: string }) {
  return <div className="empty-workspace"><strong>{title}</strong><span>{text}</span></div>;
}

export function ErrorBanner({ message }: { message?: string | null }) {
  return message ? <div className="form-alert error">{message}</div> : null;
}
