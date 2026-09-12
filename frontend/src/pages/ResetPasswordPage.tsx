import { useState, type FormEvent } from "react";
import { apiPost, ApiError } from "../api/client";
import { PublicShell } from "../public/PublicShell";

export function ResetPasswordPage() {
  const token = new URLSearchParams(window.location.search).get("token") || "";
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(token ? null : "This password-reset link is incomplete.");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    const data = new FormData(event.currentTarget);
    setBusy(true); setError(null);
    try {
      await apiPost("/api/v1/auth/reset-password", {
        token,
        password: String(data.get("password") || ""),
        confirm_password: String(data.get("confirm_password") || ""),
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "V-SPACE could not reset your password.");
    } finally { setBusy(false); }
  }

  return <PublicShell><main className="authentication-page auth-single-page"><section className="authentication-card">
    <div className="authentication-heading"><span>Secure reset</span><h2>{done ? "Password updated" : "Choose a new password"}</h2><p>{done ? "All existing V-SPACE sessions were signed out. Sign in again with your new password." : "This one-time link expires automatically and cannot be reused."}</p></div>
    {error ? <div className="public-flash error">{error}</div> : null}
    {done ? <a className="authentication-submit auth-link-button" href="/login">Continue to log in</a> : <form className="authentication-form" onSubmit={submit}>
      <div className="authentication-field"><label>New password</label><input name="password" type="password" minLength={8} required autoComplete="new-password" /></div>
      <div className="authentication-field"><label>Confirm new password</label><input name="confirm_password" type="password" minLength={8} required autoComplete="new-password" /></div>
      <button className="authentication-submit" disabled={busy || !token}>{busy ? "Updating…" : "Reset password"}</button>
    </form>}
  </section></main></PublicShell>;
}
