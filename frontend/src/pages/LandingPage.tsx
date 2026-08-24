import { Link, Navigate } from "react-router-dom";
import { useSession } from "../auth/session";

export function LandingPage() {
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

  return (
    <div className="landing-page">
      <header className="landing-nav">
        <Link className="auth-brand" to="/">
          <span className="brand-mark">L</span>
          <span><strong>LifeOS AI</strong><small>Execution Intelligence</small></span>
        </Link>
        <nav>
          <a href="#features">Features</a>
          <a href="#how-it-works">How it works</a>
          <Link className="nav-login" to="/login">Log in</Link>
          <Link className="nav-start" to="/register">Get started</Link>
        </nav>
      </header>

      <main className="landing-hero">
        <section className="landing-copy">
          <span className="hero-badge">Personal execution intelligence</span>
          <h1>Stop managing scattered work. <em>Start executing intelligently.</em></h1>
          <p>
            LifeOS AI connects your projects, tasks, notes and documents, then
            helps you decide what to work on next and why.
          </p>
          <div className="hero-actions">
            <Link className="primary-button landing-primary" to="/register">Build Your Workspace</Link>
            <a className="secondary-button" href="#features">Explore Features</a>
          </div>
        </section>

        <section className="workspace-preview" aria-label="LifeOS dashboard preview">
          <div className="preview-window-bar"><i /><i /><i /><span>LifeOS Workspace</span></div>
          <div className="preview-body">
            <aside><span className="brand-mark small">L</span><b /><b /><b /><b /></aside>
            <div className="preview-main">
              <div className="preview-greeting">GOOD EVENING</div>
              <h2>Your Execution Dashboard</h2>
              <div className="preview-stats">
                <div><span>Projects</span><strong>6</strong></div>
                <div><span>Tasks</span><strong>24</strong></div>
                <div><span>Completed</span><strong>68%</strong></div>
              </div>
              <div className="preview-focus">
                <span>SMART PRIORITY</span>
                <strong>Connect your next meaningful action</strong>
                <small>High importance · Clear execution signal</small>
                <b><i /></b>
              </div>
              <div className="preview-bottom"><div /><div /></div>
            </div>
          </div>
        </section>
      </main>

      <section className="landing-features" id="features">
        <article><strong>Projects + Tasks</strong><span>Keep goals, execution and priorities connected.</span></article>
        <article><strong>Document Brain</strong><span>Ask grounded questions with traceable evidence.</span></article>
        <article><strong>Execution Focus</strong><span>Use real workspace signals to choose what matters next.</span></article>
      </section>

      <section className="landing-how" id="how-it-works">
        <span className="eyebrow">How it works</span>
        <h2>One workspace. Shared context. Better decisions.</h2>
      </section>
    </div>
  );
}
