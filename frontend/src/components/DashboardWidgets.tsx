import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../api/client";
import { BrandMark, Icon } from "./VSpaceUi";

export function DashboardAsk() {
  const prompts = ["What should I focus on today?", "What’s blocking my projects?", "Plan the rest of my week."];
  return <section className="vs-dashboard-ask" aria-label="Ask V-SPACE"><div className="vs-ask-intro"><span className="vs-ask-mark"><BrandMark/></span><div><span className="workspace-eyebrow">A little clarity goes a long way</span><h2>What’s on your mind?</h2></div><span className="vs-ai-label"><Icon name="shield"/>You stay in control</span></div><form action="/ask" method="get" className="vs-home-composer"><input name="q" required maxLength={1200} aria-label="Ask about your workspace" placeholder="Ask anything about your workspace…"/><button type="submit" aria-label="Continue in Ask V-SPACE"><Icon name="arrow"/></button></form><div className="vs-home-prompts">{prompts.map(prompt => <a key={prompt} href={`/ask?q=${encodeURIComponent(prompt)}`}>{prompt}<Icon name="arrow"/></a>)}</div></section>;
}
type MiniBlock = { title: string; start_time: string; end_time: string; minutes: number; state?: string; project_title: string | null };
type MiniDay = { date: string; blocks: MiniBlock[]; available_minutes?: number; scheduled_minutes?: number };
type MiniPlanner = { planner: { active_plan: { days: MiniDay[] } | null } };
const duration = (n: number) => n >= 60 ? `${Math.floor(n/60)}h${n%60 ? ` ${n%60}m` : ""}` : `${n}m`;
export function TodayPlanPreview({ date }: { date: string }) {
  const query = useQuery({ queryKey: ["vspace", "today-plan", date], queryFn: () => apiGet<MiniPlanner>(`/api/v1/planner?date=${encodeURIComponent(date)}`), retry: false });
  const day = query.data?.planner?.active_plan?.days.find(d => d.date === date);
  const scheduled = day?.scheduled_minutes ?? day?.blocks.reduce((sum, b) => sum + b.minutes, 0) ?? 0;
  return <article className="dashboard-panel vs-today-plan"><div className="dashboard-panel-heading"><div><span className="panel-kicker">Make space for what matters</span><h2>Today’s plan</h2></div><span className="vs-panel-icon"><Icon name="calendar"/></span></div>
    {query.isPending ? <div className="vs-mini-loading" role="status">Loading your schedule…</div> : query.isError ? <div className="vs-plan-empty"><Icon name="calendar"/><h3>Let’s check your schedule.</h3><p>We couldn’t load your plan right now.</p><button type="button" className="workspace-secondary-button" onClick={() => void query.refetch()}>Try again</button></div> : day?.blocks.length ? <><div className="vs-plan-total"><strong>{duration(scheduled)}</strong><span>planned today</span></div><div className="vs-mini-timeline">{day.blocks.slice(0, 3).map((block, i) => <a className={`vs-mini-block ${block.state === "current" ? "current" : ""}`} href="/planner" key={`${block.start_time}-${i}`}><time>{block.start_time}</time><div><strong>{block.title}</strong><span>{block.project_title || "Personal workspace"} · {duration(block.minutes)}</span></div></a>)}</div></> : <div className="vs-plan-empty"><span className="vs-panel-icon"><Icon name="calendar"/></span><h3>A good day starts with a little space.</h3><p>Bring your priorities and fixed commitments into one realistic plan.</p></div>}
    <a href="/planner" className="workspace-secondary-button vs-full-button">{day?.blocks.length ? "View today’s plan" : "Plan my day"}<Icon name="arrow"/></a>
  </article>;
}
type RecentItem = { id: number; title?: string; filename?: string; updated_at?: string | null; uploaded_at?: string | null; project?: { title: string } | null };
export function RecentKnowledge() {
  const query = useQuery({ queryKey: ["vspace", "recent-knowledge"], retry: false, queryFn: async () => {
    const results = await Promise.allSettled([apiGet<{ items: RecentItem[] }>("/api/v1/documents"), apiGet<{ items: RecentItem[] }>("/api/v1/notes")]);
    const items = results.flatMap((r, i) => r.status === "fulfilled" && Array.isArray(r.value?.items) ? r.value.items.map(item => ({ ...item, type: i === 0 ? "document" : "note", date: item.updated_at || item.uploaded_at || "" })) : []);
    return { items: items.sort((a,b) => b.date.localeCompare(a.date)).slice(0,4), unavailable: results.some(r => r.status === "rejected") };
  } });
  return <section className="dashboard-panel vs-recent-knowledge"><div className="dashboard-panel-heading"><div><span className="panel-kicker">Pick up where you left off</span><h2>Recent knowledge</h2></div><a className="panel-link" href="/documents">Open Document Brain <span aria-hidden="true">→</span></a></div>
    {query.isPending ? <p role="status">Loading your latest documents and notes…</p> : query.data?.items.length ? <div className="vs-knowledge-grid">{query.data.items.map(item => <a href={item.type === "document" ? `/documents/${item.id}` : `/notes/${item.id}`} key={`${item.type}-${item.id}`}><span className="vs-command-icon"><Icon name={item.type === "document" ? "documents" : "notes"}/></span><div><strong>{item.title || item.filename}</strong><span>{item.type === "document" ? "PDF" : "Note"} · {item.project?.title || "Your workspace"}</span></div><Icon name="chevron"/></a>)}</div> : <div className="vs-knowledge-empty"><p>{query.data?.unavailable || query.isError ? "We couldn’t load your recent knowledge." : "Save a note or upload a document to start connecting your ideas."}</p><a href="/notes#new-note" className="workspace-secondary-button">Create a note</a></div>}
    {query.data?.unavailable ? <small className="vs-warning-text">Some recent items couldn’t be loaded.</small> : null}
  </section>;
}
