import { useState } from "react";
import { apiPost, ApiError } from "../api/client";
import { PublicShell } from "../public/PublicShell";

export function VerifyEmailPage() {
  const token = new URLSearchParams(window.location.search).get("token") || "";
  const [busy, setBusy] = useState(false);
  const [verified, setVerified] = useState(false);
  const [error, setError] = useState<string | null>(token ? null : "This verification link is incomplete.");

  async function verify() {
    if (!token || busy) return;
    setBusy(true); setError(null);
    try {
      await apiPost("/api/v1/auth/email-verification/confirm", { token });
      setVerified(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "V-SPACE could not verify this email.");
    } finally { setBusy(false); }
  }

  return <PublicShell><main className="authentication-page auth-single-page"><section className="authentication-card">
    <div className="authentication-heading"><span>Email security</span><h2>{verified ? "Email verified" : "Verify your email"}</h2><p>{verified ? "Your V-SPACE account now has a verified email address." : "Confirm that this email belongs to you. The link can only be used once."}</p></div>
    {error ? <div className="public-flash error">{error}</div> : null}
    {verified ? <a className="authentication-submit auth-link-button" href="/dashboard">Open V-SPACE</a> : <button type="button" className="authentication-submit" onClick={() => void verify()} disabled={busy || !token}>{busy ? "Verifying…" : "Verify email"}</button>}
  </section></main></PublicShell>;
}
