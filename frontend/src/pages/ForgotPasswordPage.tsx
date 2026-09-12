import { useState, type FormEvent } from "react";
import { apiPost, ApiError } from "../api/client";
import { PublicShell } from "../public/PublicShell";

export function ForgotPasswordPage() {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true); setError(null); setMessage(null);
    try {
      const result = await apiPost<{ accepted: boolean; message: string }>("/api/v1/auth/forgot-password", {
        email: String(data.get("email") || ""),
      });
      setMessage(result.message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "V-SPACE could not start password recovery.");
    } finally { setBusy(false); }
  }

  return <PublicShell><main className="authentication-page auth-single-page">
    <section className="authentication-card">
      <div className="authentication-heading"><span>Account recovery</span><h2>Reset your password</h2><p>Enter your V-SPACE email. For privacy, the response is the same whether or not an account exists.</p></div>
      {message ? <div className="public-flash success">{message}</div> : null}
      {error ? <div className="public-flash error">{error}</div> : null}
      <form className="authentication-form" onSubmit={submit}>
        <div className="authentication-field"><label htmlFor="recovery-email">Email address</label><input id="recovery-email" name="email" type="email" required autoComplete="email" placeholder="name@example.com" /></div>
        <button className="authentication-submit" disabled={busy}>{busy ? "Sending…" : "Send reset instructions"}</button>
      </form>
      <p className="authentication-switch"><a href="/login">Back to log in</a></p>
    </section>
  </main></PublicShell>;
}
