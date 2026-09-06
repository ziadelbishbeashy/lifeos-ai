import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiGet, apiPatch, ApiError } from "../api/client";
import type { ExperienceDefinition, ExperienceKey, ExperienceProfile } from "../api/types";
import { useSession } from "../auth/session";
import { navigate } from "../core/navigation";
import { ExperienceSelector, FALLBACK_EXPERIENCE_OPTIONS } from "../features/experience/ExperienceSelector";
import { PublicShell } from "../public/PublicShell";

function safeNext() {
  const value = new URLSearchParams(window.location.search).get("next") || "/dashboard";
  return value.startsWith("/") && !value.startsWith("//") && value !== "/onboarding" ? value : "/dashboard";
}

export function ExperienceOnboardingPage() {
  const session = useSession();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<ExperienceKey | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const optionsQuery = useQuery({
    queryKey: ["experience-options"],
    queryFn: () => apiGet<{ experiences: ExperienceDefinition[] }>("/api/v1/experience/options"),
    staleTime: 10 * 60_000,
    retry: false,
  });

  useEffect(() => {
    if (session.isPending) return;
    if (!session.data?.authenticated || !session.data.user) {
      navigate(`/login?next=${encodeURIComponent(safeNext())}`, true);
      return;
    }
    if (session.data.user.experience.onboarding_completed) {
      navigate(safeNext(), true);
    }
  }, [session.isPending, session.data]);

  const options = optionsQuery.data?.experiences?.length ? optionsQuery.data.experiences : FALLBACK_EXPERIENCE_OPTIONS;
  const user = session.data?.user;

  async function save() {
    if (!selected || busy) return;
    setBusy(true);
    setError(null);
    try {
      await apiPatch<{ experience: ExperienceProfile }>("/api/v1/experience/profile", {
        primary_experience: selected,
        enabled_experiences: [selected],
      });
      await queryClient.invalidateQueries({ queryKey: ["session"] });
      await session.refetch();
      navigate(safeNext(), true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "LifeOS could not save your experience.");
    } finally {
      setBusy(false);
    }
  }

  if (!user) return <PublicShell><main className="experience-onboarding-shell"><div className="experience-onboarding-card"><span className="hero-label">Opening LifeOS</span><h1>Loading your workspace…</h1></div></main></PublicShell>;

  return <PublicShell><main className="experience-onboarding-shell">
    <section className="experience-onboarding-card">
      <div className="experience-onboarding-heading">
        <span className="hero-label">Welcome, {user.name.split(/\s+/)[0]}</span>
        <h1>How will you mainly use LifeOS?</h1>
        <p>This does not create a different app. It only tunes what LifeOS emphasizes first. All of your core workspace tools remain connected.</p>
      </div>
      <ExperienceSelector options={options} selected={selected} onChange={setSelected} />
      {error ? <div className="public-flash error">{error}</div> : null}
      <div className="experience-onboarding-footer">
        <span>You can change this later in Settings and enable additional experiences.</span>
        <button type="button" className="authentication-submit" disabled={!selected || busy} onClick={() => void save()}>{busy ? "Saving…" : "Continue to LifeOS"}</button>
      </div>
    </section>
  </main></PublicShell>;
}
