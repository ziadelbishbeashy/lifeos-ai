import { useSession } from "../auth/session";
import { navigate } from "../core/navigation";
export function LandingPage() {
  const session = useSession();
  if (session.data?.authenticated) { navigate("/dashboard", true); return null; }
  return <main className="landing-native"><header className="landing-nav"><a className="auth-brand" href="/"><span className="brand-mark">L</span><span><strong>LifeOS AI</strong><small>Personal operating system</small></span></a><nav><a href="/login">Log in</a><a className="primary-button" href="/register">Get started</a></nav></header><section className="landing-hero"><span className="eyebrow">TRUSTED CONTEXT → USEFUL ACTION</span><h1>Your work, knowledge and AI<br/><em>in one operating system.</em></h1><p>Organize projects, notes, tasks, documents and focused work while keeping AI answers grounded in your own evidence.</p><div className="hero-actions"><a className="primary-button" href="/register">Build your workspace</a><a className="secondary-button" href="/login">Open LifeOS</a></div></section></main>;
}
