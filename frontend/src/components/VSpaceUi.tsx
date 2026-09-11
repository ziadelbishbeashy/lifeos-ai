import { useEffect, useId, useRef, type ReactNode } from "react";

const iconPaths = {
  dashboard: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  spark: "m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4L12 3ZM20 2v4m-2-2h4",
  projects: "M3 7V5a1 1 0 0 1 1-1h5l2 3h9a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7Z",
  tasks: "m3 6 1.5 1.5L7 5m3 1h11M3 12h4m3 0h11M3 18h4m3 0h11",
  calendar: "M7 2v4m10-4v4M3 9h18M5 4h14a2 2 0 0 1 2 2v14H3V6a2 2 0 0 1 2-2ZM7 13h2m4 0h2m-8 4h2",
  focus: "M12 8v4l3 2M8 2h8m-4 0v3M21 13a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  documents: "M14 3H5v18h14V8l-5-5Zm0 0v5h5M8 12h8m-8 4h5",
  book: "M12 6C9 3 5 3 2 4v15c4-1 7 0 10 2m0-15c3-3 7-3 10-2v15c-4-1-7 0-10 2V6Z",
  notes: "M14 3H4v18h16V11M8 12l10-10 4 4-10 10H8v-4Z",
  automation: "M4 3h6v6H4zM14 15h6v6h-6zM7 9v7a2 2 0 0 0 2 2h5m-1-13h7m-3-3 3 3-3 3",
  memory: "M9 3a3 3 0 0 0-3 3 4 4 0 0 0-3 7 4 4 0 0 0 3 6 3 3 0 0 0 6 1V6a3 3 0 0 0-3-3Zm6 0a3 3 0 0 1 3 3 4 4 0 0 1 3 7 4 4 0 0 1-3 6 3 3 0 0 1-6 1M6 6l2 2m-2 11 2-2m10-9-2 2m2 9-2-2",
  analytics: "M3 3v18h18M7 16v-5m5 5V6m5 10v-7",
  settings: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM9 3h6l1 3 3 1 3 5-2 2v4l-5 3-3-1-3 1-5-3v-4l-2-2 3-5 3-1 1-3Z",
  bell: "M18 8a6 6 0 0 0-12 0c0 8-3 8-3 10h18c0-2-3-2-3-10M10 21h4",
  search: "M10.5 3a7.5 7.5 0 1 0 0 15 7.5 7.5 0 0 0 0-15ZM16 16l5 5",
  plus: "M12 5v14M5 12h14", close: "m6 6 12 12M6 18 18 6",
  arrow: "M4 12h16m-6-6 6 6-6 6", chevron: "m9 5 7 7-7 7",
  collapse: "M3 4h18v16H3zM9 4v16m7-12-3 4 3 4", menu: "M4 6h16M4 12h16M4 18h16",
  check: "m5 12 4 4L19 6", shield: "M12 3 3 6v6c0 5 9 9 9 9s9-4 9-9V6l-9-3Zm-4 9 3 3 5-6",
  grid: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z", list: "M3 5h2m4 0h12M3 12h2m4 0h12M3 19h2m4 0h12",
  sun: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1",
  moon: "M20 14A8 8 0 0 1 10 4a8.5 8.5 0 1 0 10 10Z",
  upload: "M12 16V3m-5 5 5-5 5 5M3 16v5h18v-5", clock: "M12 8v4l4 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
} as const;
export type IconName = keyof typeof iconPaths;
export function Icon({ name, className = "" }: { name: IconName; className?: string }) {
  return <svg className={`vs-icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={iconPaths[name]} /></svg>;
}
// Replaceable book/V glyph; original brand artwork was not in the archive.
export function BrandMark() {
  return <svg className="vs-brand-symbol" viewBox="0 0 36 36" fill="none" aria-hidden="true"><path d="M18 12C14 8 9 8 4 9v17c5-1 10 0 14 4m0-18c4-4 9-4 14-3v17c-5-1-10 0-14 4V12Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"/><path d="m26 2 1.4 3.6L31 7l-3.6 1.4L26 12l-1.4-3.6L21 7l3.6-1.4L26 2Z" fill="currentColor"/><path d="m9 15 5 2m-5 3 5 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>;
}
export function Modal({ title, children, onClose, drawer = false, busy = false, className = "" }: { title: string; children: ReactNode; onClose: () => void; drawer?: boolean; busy?: boolean; className?: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const dialog = ref.current, previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    dialog?.showModal(); dialog?.querySelector<HTMLElement>("[data-autofocus]")?.focus(); document.body.style.overflow = "hidden";
    return () => { dialog?.close(); document.body.style.overflow = overflow; previous?.focus(); };
  }, []);
  return <dialog ref={ref} className={`vs-modal ${drawer ? "vs-drawer" : ""} ${className}`} aria-labelledby={id}
    onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}
    onClick={event => { if (event.target === event.currentTarget && !busy) { const r = event.currentTarget.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) onClose(); } }}>
    <header className="vs-modal-header"><div><span className="workspace-eyebrow">Your workspace</span><h2 id={id}>{title}</h2></div><button type="button" className="vs-icon-button" aria-label={`Close ${title}`} onClick={onClose} disabled={busy}><Icon name="close"/></button></header>{children}
  </dialog>;
}
export function PageSkeleton({ label = "Loading your workspace…" }: { label?: string }) {
  return <div className="vs-page-skeleton" role="status" aria-label={label}><span className="vs-sr-only">{label}</span><div className="vs-skeleton-line title"/><div className="vs-skeleton-line subtitle"/><div className="vs-skeleton-grid">{[0,1,2].map(n => <div className="vs-skeleton-card" key={n}><div className="vs-skeleton-line"/><div className="vs-skeleton-line short"/></div>)}</div></div>;
}
