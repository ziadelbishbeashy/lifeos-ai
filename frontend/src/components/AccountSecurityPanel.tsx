import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPost, ApiError, resetCsrfToken } from "../api/client";
import { startGoogleAuth } from "../auth/session";

export type AccountSecurityState = {
  email: string;
  email_verified: boolean;
  email_verified_at: string | null;
  has_password: boolean;
  google_available: boolean;
  google_connected: boolean;
  google_email: string | null;
  sessions: Array<{
    id: number;
    current: boolean;
    device: string;
    auth_method: string;
    remember: boolean;
    created_at: string | null;
    last_seen_at: string | null;
    expires_at: string | null;
  }>;
};

function readableDate(value: string | null) {
  if (!value) return "Unknown";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}

export function AccountSecurityPanel() {
  const queryClient = useQueryClient();
  const security = useQuery({
    queryKey: ["account-security"],
    queryFn: () => apiGet<{ security: AccountSecurityState }>("/api/v1/auth/security"),
    staleTime: 15_000,
    retry: false,
  });
  const queryParams = new URLSearchParams(window.location.search);
  const [message, setMessage] = useState<string | null>(queryParams.get("google_connected") === "1" ? "Google sign-in connected." : null);
  const [error, setError] = useState<string | null>(queryParams.get("google_error"));
  const [busy, setBusy] = useState<string | null>(null);

  const state = security.data?.security;

  async function refresh(messageText?: string) {
    await queryClient.invalidateQueries({ queryKey: ["account-security"] });
    await queryClient.invalidateQueries({ queryKey: ["session"] });
    if (messageText) setMessage(messageText);
  }

  async function resendVerification() {
    setBusy("verify"); setError(null); setMessage(null);
    try {
      const result = await apiPost<{ message: string }>("/api/v1/auth/email-verification/request");
      setMessage(result.message);
    } catch (err) { setError(err instanceof ApiError ? err.message : "Could not send verification email."); }
    finally { setBusy(null); }
  }

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy("password"); setError(null); setMessage(null);
    try {
      const result = await apiPost<{ message: string }>("/api/v1/auth/password/change", {
        current_password: String(data.get("current_password") || ""),
        password: String(data.get("password") || ""),
        confirm_password: String(data.get("confirm_password") || ""),
      });
      resetCsrfToken();
      event.currentTarget.reset();
      await refresh(result.message);
    } catch (err) { setError(err instanceof ApiError ? err.message : "Could not update password."); }
    finally { setBusy(null); }
  }

  async function revokeOthers() {
    setBusy("sessions"); setError(null); setMessage(null);
    try {
      const result = await apiPost<{ revoked: number }>("/api/v1/auth/sessions/revoke-others");
      await refresh(result.revoked ? `Signed out ${result.revoked} other session${result.revoked === 1 ? "" : "s"}.` : "No other active sessions were found.");
    } catch (err) { setError(err instanceof ApiError ? err.message : "Could not sign out other sessions."); }
    finally { setBusy(null); }
  }

  async function revokeOne(id: number) {
    setBusy(`session-${id}`); setError(null); setMessage(null);
    try {
      await apiDelete(`/api/v1/auth/sessions/${id}`);
      await refresh("Session signed out.");
    } catch (err) { setError(err instanceof ApiError ? err.message : "Could not end that session."); }
    finally { setBusy(null); }
  }

  async function disconnectGoogle() {
    setBusy("google"); setError(null); setMessage(null);
    try {
      await apiPost("/api/v1/auth/google/disconnect");
      await refresh("Google sign-in disconnected.");
    } catch (err) { setError(err instanceof ApiError ? err.message : "Could not disconnect Google."); }
    finally { setBusy(null); }
  }

  if (security.isPending) return <article className="experience-settings-panel security-settings-panel"><div className="experience-settings-copy"><span>Account & security</span><h2>Checking your sign-in security…</h2></div></article>;
  if (!state) return <article className="experience-settings-panel security-settings-panel"><div className="experience-settings-copy"><span>Account & security</span><h2>Security settings unavailable</h2><p>V-SPACE could not load this account's security state.</p></div></article>;

  return <section className="security-settings-stack">
    <article className="experience-settings-panel security-settings-panel">
      <div className="experience-settings-copy"><span>Account & security</span><h2>Protect your V-SPACE account</h2><p>Manage verified email, sign-in methods, password and revocable browser sessions.</p></div>
      {message ? <div className="experience-settings-message success">{message}</div> : null}
      {error ? <div className="experience-settings-message error">{error}</div> : null}
      <div className="security-status-grid">
        <div><span>Email</span><strong>{state.email}</strong><small>{state.email_verified ? "Verified" : "Not verified yet"}</small>{!state.email_verified ? <button type="button" className="secondary-button" onClick={() => void resendVerification()} disabled={busy === "verify"}>{busy === "verify" ? "Sending…" : "Resend verification"}</button> : null}</div>
        <div><span>Google</span><strong>{state.google_connected ? "Connected" : "Not connected"}</strong><small>{state.google_email || "Use Google as a secure sign-in method."}</small>{state.google_connected ? <button type="button" className="secondary-button" onClick={() => void disconnectGoogle()} disabled={busy === "google"}>{busy === "google" ? "Disconnecting…" : "Disconnect Google"}</button> : state.google_available ? <button type="button" className="secondary-button security-link-button" onClick={() => void startGoogleAuth({ mode: "link", next: "/settings" }).catch((err) => setError(err instanceof ApiError ? err.message : "Google connection could not start."))}>Connect Google</button> : <small>Google sign-in will appear after OAuth credentials are configured.</small>}</div>
      </div>
    </article>

    <article className="experience-settings-panel security-settings-panel">
      <div className="experience-settings-copy"><span>Password</span><h2>{state.has_password ? "Change password" : "Create a password"}</h2><p>{state.has_password ? "Changing your password signs out your other active V-SPACE sessions." : "Add email/password as a backup sign-in method for this account."}</p></div>
      <form className="security-password-form" onSubmit={changePassword}>
        {state.has_password ? <label><span>Current password</span><input name="current_password" type="password" required autoComplete="current-password" /></label> : null}
        <label><span>New password</span><input name="password" type="password" required minLength={8} autoComplete="new-password" /></label>
        <label><span>Confirm new password</span><input name="confirm_password" type="password" required minLength={8} autoComplete="new-password" /></label>
        <button className="primary-button" disabled={busy === "password"}>{busy === "password" ? "Updating…" : state.has_password ? "Change password" : "Create password"}</button>
      </form>
    </article>

    <article className="experience-settings-panel security-settings-panel">
      <div className="security-session-heading"><div className="experience-settings-copy"><span>Sessions</span><h2>Where you're signed in</h2><p>V-SPACE sessions are revocable on the server. Password resets revoke every active session automatically.</p></div><button type="button" className="secondary-button" onClick={() => void revokeOthers()} disabled={busy === "sessions"}>{busy === "sessions" ? "Signing out…" : "Sign out other sessions"}</button></div>
      <div className="security-session-list">{state.sessions.map((item) => <div className={`security-session-row ${item.current ? "current" : ""}`} key={item.id}><div><strong>{item.device}</strong><small>{item.current ? "Current session" : `Last active ${readableDate(item.last_seen_at)}`} · {item.auth_method === "google" ? "Google" : "Password"}{item.remember ? " · remembered" : ""}</small></div>{item.current ? <span className="security-current-badge">Current</span> : <button type="button" className="secondary-button" onClick={() => void revokeOne(item.id)} disabled={busy === `session-${item.id}`}>{busy === `session-${item.id}` ? "Ending…" : "Sign out"}</button>}</div>)}</div>
    </article>
  </section>;
}
