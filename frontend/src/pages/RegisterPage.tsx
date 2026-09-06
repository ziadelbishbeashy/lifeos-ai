import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { apiGet, ApiError } from "../api/client";
import type { ExperienceDefinition, ExperienceKey } from "../api/types";
import { register } from "../auth/session";
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
  const options = optionsQuery.data?.experiences?.length ? optionsQuery.data.experiences : FALLBACK_EXPERIENCE_OPTIONS;

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!experience) {
      setError("Choose how you mainly want to use LifeOS.");
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
      <h1>One LifeOS, tuned to how you work.</h1>
      <p>Your choice changes defaults and recommendations, not the underlying LifeOS platform. You can change it later.</p>
      <div className="authentication-benefits"><span>Same projects, tasks and knowledge core</span><span>Adaptive Home and Ask LifeOS suggestions</span><span>No separate app or locked account type</span></div>
    </section>
    <section className="authentication-card experience-registration-card">
      <div className="authentication-heading"><span>Step 1 · Your experience</span><h2>What will you mainly use LifeOS for?</h2><p>This sets your starting experience. You can enable other experiences later.</p></div>
      <ExperienceSelector options={options} selected={experience} onChange={setExperience} compact />
      {error ? <div className="public-flash error">{error}</div> : null}
      <form className="authentication-form" onSubmit={submit}>
        <div className="experience-account-divider"><span>Step 2</span><strong>Create your account</strong></div>
        <div className="authentication-field"><label>Name</label><input name="name" required autoComplete="name" placeholder="Your name" /></div>
        <div className="authentication-field"><label>Email address</label><input name="email" type="email" required autoComplete="email" placeholder="name@example.com" /></div>
        <div className="authentication-field"><label>Password</label><input name="password" type="password" required autoComplete="new-password" placeholder="Create a password" /></div>
        <div className="authentication-field"><label>Confirm password</label><input name="confirm_password" type="password" required autoComplete="new-password" placeholder="Repeat your password" /></div>
        <button className="authentication-submit" disabled={busy || !experience}>{busy ? "Creating…" : "Create LifeOS account"}</button>
      </form>
      <p className="authentication-switch">Already have an account? <a href="/login">Log in</a></p>
    </section>
  </main></PublicShell>;
}
