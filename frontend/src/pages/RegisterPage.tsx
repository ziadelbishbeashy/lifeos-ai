import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { apiGet, ApiError } from "../api/client";
import type { ExperienceDefinition, ExperienceKey } from "../api/types";
import { register, startGoogleAuth } from "../auth/session";
import { navigate } from "../core/navigation";
import { ExperienceSelector, FALLBACK_EXPERIENCE_OPTIONS } from "../features/experience/ExperienceSelector";
import { PublicShell } from "../public/PublicShell";

export function RegisterPage() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [experience, setExperience] = useState<ExperienceKey | null>(null);
  const optionsQuery = useQuery({
    queryKey: ["experience-options"],
    queryFn: () => apiGet<{ experiences: ExperienceDefinition[] }>("/api/v1/experience/options"),
    staleTime: 10 * 60_000,
    retry: false,
  });
  const authConfig = useQuery({
    queryKey: ["auth-public-config"],
    queryFn: () => apiGet<{ google_enabled: boolean }>("/api/v1/auth/config"),
    staleTime: 5 * 60_000,
    retry: false,
  });
  const options = optionsQuery.data?.experiences?.length ? optionsQuery.data.experiences : FALLBACK_EXPERIENCE_OPTIONS;

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!experience) {
      setError("Choose how you mainly want to use V-SPACE.");
      return;
    }
    const d = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const result = await register({
        name: String(d.get("name") || ""),
        email: String(d.get("email") || ""),
        password: String(d.get("password") || ""),
        confirm_password: String(d.get("confirm_password") || ""),
        primary_experience: String(experience),
      });
      navigate(result.user?.experience.onboarding_completed ? "/dashboard" : "/onboarding", true);
    } catch (x) {
      setError(x instanceof ApiError ? x.message : "Account creation failed.");
    } finally {
      setBusy(false);
    }
  }

  return <PublicShell><main className="authentication-page experience-registration-page">
    <section className="authentication-introduction">
      <span className="hero-label">Create your workspace</span>
      <h1>One V-SPACE, tuned to how you work.</h1>
      <p>Google sign-in can create your account quickly, or choose your starting experience and create a password.</p>
      <div className="authentication-benefits"><span>Same projects, tasks and knowledge core</span><span>Adaptive Home and Ask V-SPACE suggestions</span><span>Private account and revocable sessions</span></div>
    </section>
    <section className="authentication-card experience-registration-card">
      <div className="authentication-heading"><span>V-SPACE account</span><h2>Create your account</h2><p>You can personalize the workspace after sign-up.</p></div>
      {authConfig.data?.google_enabled ? <><button type="button" className="google-auth-button" onClick={() => void startGoogleAuth({ next: "/dashboard" }).catch((x) => setError(x instanceof ApiError ? x.message : "Google sign-in could not start."))}><span className="google-auth-mark">G</span><strong>Continue with Google</strong></button><div className="auth-divider"><span>or create with email</span></div></> : null}
      <div className="authentication-heading experience-auth-subheading"><span>Step 1 · Your experience</span><h2>What will you mainly use V-SPACE for?</h2><p>This sets your starting experience. You can change it later.</p></div>
      <ExperienceSelector options={options} selected={experience} onChange={setExperience} compact />
      {error ? <div className="public-flash error">{error}</div> : null}
      <form className="authentication-form" onSubmit={submit}>
        <div className="experience-account-divider"><span>Step 2</span><strong>Create your account</strong></div>
        <div className="authentication-field"><label>Name</label><input name="name" required autoComplete="name" placeholder="Your name" /></div>
        <div className="authentication-field"><label>Email address</label><input name="email" type="email" required autoComplete="email" placeholder="name@example.com" /></div>
        <div className="authentication-field"><label>Password</label><input name="password" type="password" minLength={8} required autoComplete="new-password" placeholder="Create a password" /></div>
        <div className="authentication-field"><label>Confirm password</label><input name="confirm_password" type="password" minLength={8} required autoComplete="new-password" placeholder="Repeat your password" /></div>
        <button className="authentication-submit" disabled={busy || !experience}>{busy ? "Creating…" : "Create V-SPACE account"}</button>
      </form>
      <p className="authentication-switch">Already have an account? <a href="/login">Log in</a></p>
    </section>
  </main></PublicShell>;
}
