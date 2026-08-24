import { useState, type FormEvent } from "react";
import { register } from "../auth/session";
import { navigate } from "../core/navigation";
import { ApiError } from "../api/client";

export function RegisterPage() {
  const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget); setBusy(true); setError(null);
    try { await register({ name: String(data.get("name") || ""), email: String(data.get("email") || ""), password: String(data.get("password") || ""), confirm_password: String(data.get("confirm_password") || "") }); navigate("/dashboard", true); }
    catch (failure) { setError(failure instanceof ApiError ? failure.message : "Account creation failed."); }
    finally { setBusy(false); }
  }
  return <main className="auth-page"><section className="auth-story"><a className="auth-brand" href="/"><span className="brand-mark">L</span><span><strong>LifeOS AI</strong><small>Build a trusted workspace</small></span></a><div className="auth-story-copy"><span className="eyebrow">Start organized</span><h1>Build a workspace that <em>remembers context.</em></h1><p>Connect goals, execution, knowledge and grounded AI without losing evidence or history.</p></div></section><section className="auth-panel"><div className="auth-card"><span className="eyebrow">Create workspace</span><h2>Create account</h2>{error ? <div className="form-alert error">{error}</div> : null}<form className="auth-form" onSubmit={submit}><label>Name<input name="name" required autoComplete="name" /></label><label>Email<input name="email" type="email" required autoComplete="email" /></label><label>Password<input name="password" type="password" required autoComplete="new-password" /></label><label>Confirm password<input name="confirm_password" type="password" required autoComplete="new-password" /></label><button className="primary-button auth-submit" disabled={busy}>{busy ? "Creating…" : "Create account"}</button></form><p className="auth-switch">Already have an account? <a href="/login">Log in</a></p></div></section></main>;
}
