import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiPatch, ApiError } from "../api/client";
import type { ExperienceKey, ExperienceProfile } from "../api/types";
import { useSession } from "../auth/session";
import { ExperienceSelector } from "../features/experience/ExperienceSelector";
import { PersonalizationSettingsPanel } from "../components/PersonalizationProfile";
import { AccountSecurityPanel } from "../components/AccountSecurityPanel";

export function ExperienceSettingsPage() {
  const session = useSession();
  const queryClient = useQueryClient();
  const profile = session.data?.user?.experience;
  const [primary, setPrimary] = useState<ExperienceKey | null>(profile?.primary_experience || null);
  const [enabled, setEnabled] = useState<ExperienceKey[]>(profile?.enabled_experiences || []);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!profile) return;
    setPrimary(profile.primary_experience);
    setEnabled(profile.enabled_experiences);
  }, [profile?.primary_experience, profile?.enabled_experiences.join("|")]);

  const options = profile?.available_experiences || [];
  const primaryOption = useMemo(() => options.find((item) => item.key === primary) || null, [options, primary]);

  function choosePrimary(key: ExperienceKey) {
    setPrimary(key);
    setEnabled((items) => items.includes(key) ? items : [key, ...items]);
    setMessage(null);
  }

  function toggleExtra(key: ExperienceKey) {
    if (key === primary) return;
    setEnabled((items) => items.includes(key) ? items.filter((item) => item !== key) : [...items, key]);
    setMessage(null);
  }

  async function save() {
    if (!primary || busy) return;
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      await apiPatch<{ experience: ExperienceProfile }>("/api/v1/experience/profile", {
        primary_experience: primary,
        enabled_experiences: enabled,
      });
      await queryClient.invalidateQueries({ queryKey: ["session"] });
      await session.refetch();
      setMessage("Your V-SPACE experience has been updated.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "V-SPACE could not update your experience.");
    } finally {
      setBusy(false);
    }
  }

  if (!profile) return <section className="workspace-page"><div className="dashboard-empty-state"><h3>Experience settings unavailable</h3><p>V-SPACE could not load your profile.</p></div></section>;

  return <section className="workspace-page experience-settings-page">
    <header className="workspace-page-header"><div><span className="panel-kicker">My V-SPACE</span><h1>Experience settings</h1><p>Choose what V-SPACE should emphasize without changing the underlying product or your data.</p></div></header>

    <article className="experience-settings-panel">
      <div className="experience-settings-copy"><span>Primary experience</span><h2>What should V-SPACE optimize for first?</h2><p>Your primary experience controls the default language, Home emphasis and Ask V-SPACE suggestions.</p></div>
      <ExperienceSelector options={options} selected={primary} onChange={choosePrimary} compact />
    </article>

    <article className="experience-settings-panel">
      <div className="experience-settings-copy"><span>Additional experiences</span><h2>Use more than one side of V-SPACE</h2><p>Enable extra experiences without creating another account. Your primary experience stays the default.</p></div>
      <div className="experience-toggle-list">
        {options.map((option) => {
          const checked = enabled.includes(option.key) || option.key === primary;
          return <label className={`experience-toggle-row ${option.key === primary ? "primary" : ""}`} key={option.key}>
            <input type="checkbox" checked={checked} disabled={option.key === primary} onChange={() => toggleExtra(option.key)} />
            <span><strong>{option.label}</strong><small>{option.key === primary ? "Primary experience" : option.description}</small></span>
            <em>{checked ? "Enabled" : "Off"}</em>
          </label>;
        })}
      </div>
    </article>

    <PersonalizationSettingsPanel />

    <AccountSecurityPanel />

    <article className="experience-settings-summary">
      <div><span>Current default</span><strong>{primaryOption?.label || "Not selected"}</strong><small>{primaryOption?.workspace_label || "V-SPACE workspace"}</small></div>
      <div><span>Enabled experiences</span><strong>{new Set([primary, ...enabled].filter(Boolean)).size}</strong><small>Same V-SPACE core</small></div>
      <button type="button" className="primary-button" onClick={() => void save()} disabled={!primary || busy}>{busy ? "Saving…" : "Save experience"}</button>
    </article>
    {message ? <div className="experience-settings-message success">{message}</div> : null}
    {error ? <div className="experience-settings-message error">{error}</div> : null}
  </section>;
}
