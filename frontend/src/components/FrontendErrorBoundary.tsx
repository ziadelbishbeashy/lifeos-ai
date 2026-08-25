import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { error: Error | null };

export class FrontendErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("LifeOS frontend screen crashed", error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <section className="frontend-error-card" role="alert">
        <span className="frontend-error-kicker">LifeOS recovered the page</span>
        <h2>This screen hit a frontend error.</h2>
        <p>Reload the screen. If it happens again, the browser console will contain the exact error instead of leaving a blank page.</p>
        <div className="frontend-error-actions">
          <button type="button" className="workspace-primary-button" onClick={() => window.location.reload()}>Reload screen</button>
          <a className="workspace-secondary-button" href="/dashboard">Dashboard</a>
        </div>
      </section>
    );
  }
}
