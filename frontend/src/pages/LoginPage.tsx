import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { apiGet, ApiError } from "../api/client";
import { login, startGoogleAuth } from "../auth/session";
import { navigate } from "../core/navigation";
import { PublicShell } from "../public/PublicShell";

function safeNext() {
  const v = new URLSearchParams(window.location.search).get("next") || "/dashboard";
  return v.startsWith("/") && !v.startsWith("//") ? v : "/dashboard";
}

export function LoginPage() {
  const params = new URLSearchParams(window.location.search);
  const [error, setError] = useState<string | null>(params.get("google_error"));
  const [busy, setBusy] = useState(false);
  const authConfig = useQuery({
    queryKey: ["auth-public-config"],
    queryFn: () => apiGet<{ google_enabled: boolean }>("/api/v1/auth/config"),
    staleTime: 5 * 60_000,
    retry: false,
  });

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const d = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const result = await login({
        email: String(d.get("email") || ""),
        password: String(d.get("password") || ""),
        remember: d.get("remember") !== null,
      });
      const next = safeNext();
      navigate(result.user?.experience.onboarding_completed ? next : `/onboarding?next=${encodeURIComponent(next)}`, true);
    } catch (x) {
      setError(x instanceof ApiError ? x.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  return <PublicShell><main className="authentication-page"><section className="authentication-introduction"><span className="hero-label">Welcome back</span><h1>Continue building your intelligent workspace.</h1><p>Access your projects, tasks, notes, documents and execution plans.</p><div className="authentication-benefits"><span>Connected project knowledge</span><span>Private personal workspace</span><span>Server-revocable secure sessions</span></div></section><section className="authentication-card"><div className="authentication-heading"><span>V-SPACE account</span><h2>Log in</h2><p>Choose Google or your V-SPACE password.</p></div>{error ? <div className="public-flash error">{error}</div> : null}{authConfig.data?.google_enabled ? <><button type="button" className="google-auth-button" onClick={() => void startGoogleAuth({ next: safeNext() }).catch((x) => setError(x instanceof ApiError ? x.message : "Google sign-in could not start."))}><span className="google-auth-mark">G</span><strong>Continue with Google</strong></button><div className="auth-divider"><span>or</span></div></> : null}<form className="authentication-form" onSubmit={submit}><div className="authentication-field"><label htmlFor="email">Email address</label><input type="email" id="email" name="email" placeholder="name@example.com" autoComplete="email" required /></div><div className="authentication-field"><div className="auth-label-row"><label htmlFor="password">Password</label><a href="/forgot-password">Forgot password?</a></div><input type="password" id="password" name="password" placeholder="Enter your password" autoComplete="current-password" required /></div><label className="remember-control"><input type="checkbox" name="remember" /><span>Keep me logged in on this device</span></label><button type="submit" className="authentication-submit" disabled={busy}>{busy ? "Logging in…" : "Log In to V-SPACE"}</button></form><p className="authentication-switch">Do not have an account? <a href="/register">Create one</a></p></section></main></PublicShell>;
}
