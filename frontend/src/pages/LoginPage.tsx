import { useState, type FormEvent } from "react";
import { login } from "../auth/session";
import { navigate } from "../core/navigation";
import { ApiError } from "../api/client";

function safeNext() {
  const value = new URLSearchParams(window.location.search).get("next") || "/dashboard";
  return value.startsWith("/") && !value.startsWith("//") ? value : "/dashboard";
}

export function LoginPage() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true); setError(null);
    try {
      await login({ email: String(data.get("email") || ""), password: String(data.get("password") || ""), remember: data.get("remember") !== null });
      navigate(safeNext(), true);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Login failed.");
    } finally { setBusy(false); }
  }
  return <main className="auth-page">
    <section className="auth-story"><a className="auth-brand" href="/"><span className="brand-mark">L</span><span><strong>LifeOS AI</strong><small>Your private operating system</small></span></a><div className="auth-story-copy"><span className="eyebrow">Welcome back</span><h1>Continue where your <em>work left off.</em></h1><p>Projects, notes, documents, tasks, focus sessions and AI reasoning stay connected in one workspace.</p></div></section>
    <section className="auth-panel"><div className="auth-card"><span className="eyebrow">Secure workspace</span><h2>Log in</h2><p className="auth-card-lead">Use your LifeOS account to continue.</p>{error ? <div className="form-alert error">{error}</div> : null}<form className="auth-form" onSubmit={submit}><label>Email<input name="email" type="email" required autoComplete="email" /></label><label>Password<input name="password" type="password" required autoComplete="current-password" /></label><label className="check-row"><input name="remember" type="checkbox" /><span>Keep me signed in</span></label><button className="primary-button auth-submit" disabled={busy}>{busy ? "Logging in…" : "Log in"}</button></form><p className="auth-switch">New to LifeOS? <a href="/register">Create an account</a></p></div></section>
  </main>;
}
