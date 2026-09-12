import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiDelete, apiGet, apiPatch, apiPost } from "../api/client";
import type { PersonalizationCommitment, PersonalizationProfile, User } from "../api/types";
import { useSession } from "../auth/session";
import { formatTime12h, TimePicker12h } from "./TimePicker12h";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const PRIORITIES = [
  ["university", "🎓", "University", "Classes, assignments and grades"],
  ["projects", "💻", "Building projects", "Coding, creative or personal projects"],
  ["career", "🚀", "Career", "Skills, applications and professional growth"],
  ["fitness", "🏋️", "Fitness", "Gym, training and recovery"],
  ["business", "📈", "Business", "Clients, products and business work"],
  ["personal_time", "🌿", "Personal life", "Keep room for life outside work"],
] as const;
const PRODUCTIVE = [
  ["morning", "Morning", "I think best early in the day"],
  ["afternoon", "Afternoon", "I usually get going after midday"],
  ["evening", "Evening", "My best focus is later in the day"],
  ["late_night", "Late night", "I often do my best work at night"],
  ["varies", "It depends", "My energy changes from day to day"],
] as const;
const INTENSITY = [
  ["light", "Leave me breathing room", "Keep meaningful free space instead of filling my day"],
  ["balanced", "Productive but realistic", "A useful plan with enough room for real life"],
  ["productive", "Use most of my available time", "Keep me moving when there is work to do"],
  ["intense", "Pack the day when needed", "Use nearly all available time for high-pressure days"],
] as const;
const OVERLOAD = [
  ["defer_low_priority", "Move less important work", "Keep the important work and leave lower-priority items for another plan"],
  ["ask", "Ask me what to move", "Show me the conflict and let me decide"],
  ["leave_unscheduled", "Never overbook me", "Leave work outside the plan if it does not realistically fit"],
  ["shorten_optional", "Protect fixed work first", "Do not silently shorten important or explicit work"],
] as const;

function message(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

type Draft = {
  usual_wake_time: string;
  usual_sleep_time: string;
  productive_period: string;
  preferred_focus_minutes: number | null;
  preferred_break_minutes: number | null;
  planning_intensity: string;
  workday_start: string;
  workday_end: string;
  avoid_after_time: string;
  regular_commitments: PersonalizationCommitment[];
  priorities: string[];
  overload_behavior: string;
};

function draftFrom(profile?: PersonalizationProfile | null): Draft {
  return {
    usual_wake_time: profile?.usual_wake_time || "",
    usual_sleep_time: profile?.usual_sleep_time || "",
    productive_period: profile?.productive_period || "",
    preferred_focus_minutes: profile?.preferred_focus_minutes || null,
    preferred_break_minutes: profile?.preferred_break_minutes || null,
    planning_intensity: profile?.planning_intensity || "",
    workday_start: profile?.workday_start || "",
    workday_end: profile?.workday_end || "",
    avoid_after_time: profile?.avoid_after_time || "",
    regular_commitments: profile?.regular_commitments || [],
    priorities: profile?.priorities || [],
    overload_behavior: profile?.overload_behavior || "",
  };
}

function payload(draft: Draft) {
  return {
    ...draft,
    usual_wake_time: draft.usual_wake_time || null,
    usual_sleep_time: draft.usual_sleep_time || null,
    productive_period: draft.productive_period || null,
    preferred_focus_minutes: draft.preferred_focus_minutes,
    preferred_break_minutes: draft.preferred_break_minutes,
    workday_start: draft.workday_start || null,
    workday_end: draft.workday_end || null,
    avoid_after_time: draft.avoid_after_time || null,
    priorities: draft.priorities,
  };
}

function RichChoice({ value, options, onChange }: { value: string; options: readonly (readonly [string, string, string])[]; onChange: (value: string) => void }) {
  return <div className="personalization-rich-choices">{options.map(([key, label, description]) => <button type="button" key={key} className={value === key ? "selected" : ""} onClick={() => onChange(key)}><strong>{label}</strong><span>{description}</span></button>)}</div>;
}

function NumberChoice({ value, options, suffix, onChange, allowAuto = false }: { value: number | null; options: number[]; suffix: string; onChange: (value: number | null) => void; allowAuto?: boolean }) {
  return <div className="personalization-choice-row">{options.map(option => <button type="button" key={option} className={value === option ? "selected" : ""} onClick={() => onChange(option)}>{option}{suffix}</button>)}{allowAuto ? <button type="button" className={value === null ? "selected" : ""} onClick={() => onChange(null)}>Let V-SPACE decide</button> : null}</div>;
}

function PresetTime({ label, value, selected, onClick }: { label: string; value: string; selected: string; onClick: (value: string) => void }) {
  return <button type="button" className={selected === value ? "selected" : ""} onClick={() => onClick(value)}>{label}</button>;
}

function FriendlyTimeQuestion({ label, help, value, presets, onChange, allowEmpty = true }: { label: string; help: string; value: string; presets: Array<[string, string]>; onChange: (value: string) => void; allowEmpty?: boolean }) {
  return <div className="personalization-time-question"><div><h3>{label}</h3><p>{help}</p></div><div className="personalization-choice-row">{presets.map(([time, text]) => <PresetTime key={time} value={time} label={text} selected={value} onClick={onChange} />)}{allowEmpty ? <button type="button" className={!value ? "selected" : ""} onClick={() => onChange("")}>It changes</button> : null}</div><details className="personalization-custom-time"><summary>Choose another time</summary><TimePicker12h value={value || "09:00"} onChange={onChange} ariaLabel={label} /></details></div>;
}

function CommitmentEditor({ items, onChange }: { items: PersonalizationCommitment[]; onChange: (items: PersonalizationCommitment[]) => void }) {
  const [title, setTitle] = useState("");
  const [type, setType] = useState("other");
  const [days, setDays] = useState<number[]>([]);
  const [start, setStart] = useState("19:00");
  const [end, setEnd] = useState("20:00");
  function toggleDay(index: number) { setDays(current => current.includes(index) ? current.filter(day => day !== index) : [...current, index].sort()); }
  function add() {
    if (!title.trim() || !days.length || !start || !end || end <= start || items.length >= 12) return;
    onChange([...items, { title: title.trim().slice(0, 80), commitment_type: type, days, start_time: start, end_time: end }]);
    setTitle(""); setDays([]);
  }
  return <div className="personalization-commitment-editor">
    {items.length ? <div className="personalization-commitment-list">{items.map((item, index) => <div className="personalization-commitment-item" key={`${item.title}-${index}`}><div><strong>{item.title}</strong><span>{item.days.map(day => DAYS[day]).join(", ")} · {formatTime12h(item.start_time)}–{formatTime12h(item.end_time)}</span></div><button type="button" onClick={() => onChange(items.filter((_, itemIndex) => itemIndex !== index))}>Remove</button></div>)}</div> : <p className="personalization-empty-copy">Nothing regular yet? That is fine. V-SPACE can still plan from what you tell it each day.</p>}
    <div className="personalization-commitment-form">
      <div className="personalization-inline-fields"><label><span>What is it?</span><input value={title} onChange={event => setTitle(event.target.value)} placeholder="Gym, university, work…" /></label><label><span>Type</span><select value={type} onChange={event => setType(event.target.value)}><option value="university">University</option><option value="work">Work</option><option value="gym">Gym</option><option value="training">Training</option><option value="family">Family</option><option value="meeting">Meeting</option><option value="personal">Personal</option><option value="other">Other</option></select></label></div>
      <div><span className="personalization-field-label">Which days?</span><div className="personalization-day-row">{DAYS.map((day, index) => <button type="button" className={days.includes(index) ? "selected" : ""} key={day} onClick={() => toggleDay(index)}>{day}</button>)}</div></div>
      <div className="personalization-commitment-times"><label><span>Starts</span><TimePicker12h value={start} onChange={setStart} /></label><label><span>Ends</span><TimePicker12h value={end} onChange={setEnd} /></label></div>
      <button type="button" className="personalization-add-commitment" onClick={add}>+ Add this routine</button>
    </div>
  </div>;
}

function PrioritiesStep({ draft, setDraft }: { draft: Draft; setDraft: (next: Draft) => void }) {
  return <div className="personalization-conversation-step"><span className="personalization-step-kicker">Start with the big picture</span><h2>What do you want V-SPACE to help you manage?</h2><p>Pick everything that matters. This helps V-SPACE understand what deserves your attention — you can change it later.</p><div className="personalization-purpose-grid">{PRIORITIES.map(([key, icon, label, description]) => <button type="button" key={key} className={draft.priorities.includes(key) ? "selected" : ""} onClick={() => setDraft({ ...draft, priorities: draft.priorities.includes(key) ? draft.priorities.filter(item => item !== key) : [...draft.priorities, key] })}><span>{icon}</span><strong>{label}</strong><small>{description}</small></button>)}</div></div>;
}

function RoutineStep({ draft, setDraft }: { draft: Draft; setDraft: (next: Draft) => void }) {
  return <div className="personalization-conversation-step"><span className="personalization-step-kicker">Your normal day</span><h2>When is your day usually active?</h2><p>We use this to avoid putting focused work while you are normally asleep. These are preferences, not hard calendar events.</p><div className="personalization-two-up"><FriendlyTimeQuestion label="When do you usually wake up?" help="V-SPACE normally leaves a little time before focused work." value={draft.usual_wake_time} presets={[["07:00","7:00 AM"],["08:00","8:00 AM"],["09:00","9:00 AM"],["10:00","10:00 AM"]]} onChange={value => setDraft({ ...draft, usual_wake_time: value })} /><FriendlyTimeQuestion label="When do you usually go to sleep?" help="V-SPACE uses this as a late-day boundary unless you explicitly override it." value={draft.usual_sleep_time} presets={[["23:00","11:00 PM"],["00:00","12:00 AM"],["01:00","1:00 AM"],["02:00","2:00 AM"]]} onChange={value => setDraft({ ...draft, usual_sleep_time: value })} /></div></div>;
}

function CommitmentsStep({ draft, setDraft }: { draft: Draft; setDraft: (next: Draft) => void }) {
  return <div className="personalization-conversation-step"><span className="personalization-step-kicker">Protect your real time</span><h2>What already takes up time in a normal week?</h2><p>Add routines such as university, work or gym. Smart Planner will reserve them automatically on the days you choose.</p><CommitmentEditor items={draft.regular_commitments} onChange={items => setDraft({ ...draft, regular_commitments: items })} /></div>;
}

function ProductiveStep({ draft, setDraft }: { draft: Draft; setDraft: (next: Draft) => void }) {
  return <div className="personalization-conversation-step"><span className="personalization-step-kicker">Your energy</span><h2>When do you usually do your best thinking?</h2><p>V-SPACE will try to place harder study and deep-work blocks near this part of your day. It is a preference, not a restriction.</p><RichChoice value={draft.productive_period} options={PRODUCTIVE} onChange={value => setDraft({ ...draft, productive_period: value })} /><button type="button" className="personalization-unsure" onClick={() => setDraft({ ...draft, productive_period: "varies" })}>I am not sure — let V-SPACE stay flexible</button></div>;
}

function FocusStep({ draft, setDraft }: { draft: Draft; setDraft: (next: Draft) => void }) {
  return <div className="personalization-conversation-step"><span className="personalization-step-kicker">How you work</span><h2>What kind of focus rhythm feels natural?</h2><p>This helps V-SPACE split longer work into realistic blocks and add breaks between them.</p><div className="personalization-focus-row"><div><strong>Focused session</strong><NumberChoice value={draft.preferred_focus_minutes} options={[25,45,60,90]} suffix=" min" allowAuto onChange={value => setDraft({ ...draft, preferred_focus_minutes: value })} /></div><div><strong>Break between blocks</strong><NumberChoice value={draft.preferred_break_minutes} options={[5,10,15,20]} suffix=" min" allowAuto onChange={value => setDraft({ ...draft, preferred_break_minutes: value })} /></div></div></div>;
}

function IntensityStep({ draft, setDraft }: { draft: Draft; setDraft: (next: Draft) => void }) {
  return <div className="personalization-conversation-step"><span className="personalization-step-kicker">How full should a plan feel?</span><h2>When V-SPACE plans a normal day, what feels right?</h2><p>You can always say “light day” or “pack tomorrow” and override this for one plan.</p><RichChoice value={draft.planning_intensity} options={INTENSITY} onChange={value => setDraft({ ...draft, planning_intensity: value })} /></div>;
}

function BoundariesStep({ draft, setDraft }: { draft: Draft; setDraft: (next: Draft) => void }) {
  return <div className="personalization-conversation-step"><span className="personalization-step-kicker">One last thing</span><h2>What should V-SPACE do when real life gets crowded?</h2><p>We will never pretend impossible work fits. Choose the behavior you would rather see when there is too much to do.</p><RichChoice value={draft.overload_behavior} options={OVERLOAD} onChange={value => setDraft({ ...draft, overload_behavior: value })} /><details className="personalization-advanced-boundaries"><summary>Optional: set a usual focused-work window</summary><p>If you leave this blank, V-SPACE derives a safe window from your wake/sleep routine and uses visible assumptions.</p><div className="personalization-three-times"><label><span>Usually start focused work</span><TimePicker12h value={draft.workday_start || "09:00"} onChange={value => setDraft({ ...draft, workday_start: value })} allowEmpty /></label><label><span>Usually finish focused work</span><TimePicker12h value={draft.workday_end || "17:00"} onChange={value => setDraft({ ...draft, workday_end: value })} allowEmpty /></label><label><span>Avoid scheduling after</span><TimePicker12h value={draft.avoid_after_time || "22:00"} onChange={value => setDraft({ ...draft, avoid_after_time: value })} allowEmpty /></label></div></details></div>;
}

function OnboardingStep({ draft, setDraft, step }: { draft: Draft; setDraft: (next: Draft) => void; step: number }) {
  if (step === 1) return <PrioritiesStep draft={draft} setDraft={setDraft} />;
  if (step === 2) return <RoutineStep draft={draft} setDraft={setDraft} />;
  if (step === 3) return <CommitmentsStep draft={draft} setDraft={setDraft} />;
  if (step === 4) return <ProductiveStep draft={draft} setDraft={setDraft} />;
  if (step === 5) return <FocusStep draft={draft} setDraft={setDraft} />;
  if (step === 6) return <IntensityStep draft={draft} setDraft={setDraft} />;
  return <BoundariesStep draft={draft} setDraft={setDraft} />;
}

function SettingsEditor({ draft, setDraft, section }: { draft: Draft; setDraft: (next: Draft) => void; section: number }) {
  if (section === 1) return <div className="personalization-settings-stack"><PrioritiesStep draft={draft} setDraft={setDraft} /><RoutineStep draft={draft} setDraft={setDraft} /></div>;
  if (section === 2) return <CommitmentsStep draft={draft} setDraft={setDraft} />;
  if (section === 3) return <div className="personalization-settings-stack"><ProductiveStep draft={draft} setDraft={setDraft} /><FocusStep draft={draft} setDraft={setDraft} /><IntensityStep draft={draft} setDraft={setDraft} /></div>;
  return <BoundariesStep draft={draft} setDraft={setDraft} />;
}

export function PersonalizationOnboardingModal({ user }: { user: User }) {
  const session = useSession();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(user.personalization.onboarding_state === "not_started");
  const [started, setStarted] = useState(false);
  const [step, setStep] = useState(1);
  const [draft, setDraft] = useState<Draft>(() => draftFrom());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const profileQuery = useQuery({ queryKey: ["personalization-profile"], queryFn: () => apiGet<{ personalization: PersonalizationProfile }>("/api/v1/personalization"), enabled: open, retry: false });

  useEffect(() => { if (profileQuery.data?.personalization) setDraft(draftFrom(profileQuery.data.personalization)); }, [profileQuery.data?.personalization.updated_at]);
  useEffect(() => { setOpen(user.personalization.onboarding_state === "not_started"); }, [user.personalization.onboarding_state]);

  async function refreshAndClose() {
    await queryClient.invalidateQueries({ queryKey: ["session"] });
    await queryClient.invalidateQueries({ queryKey: ["personalization-profile"] });
    await session.refetch();
    setOpen(false);
  }
  async function defer() {
    setBusy(true); setError(null);
    try { await apiPost("/api/v1/personalization/defer", {}); await refreshAndClose(); }
    catch (err) { setError(message(err, "V-SPACE could not save that choice.")); }
    finally { setBusy(false); }
  }
  async function save() {
    setBusy(true); setError(null);
    try { await apiPatch("/api/v1/personalization", payload(draft)); await refreshAndClose(); }
    catch (err) { setError(message(err, "V-SPACE could not save your profile.")); }
    finally { setBusy(false); }
  }

  if (!open) return null;
  return <div className="personalization-modal-backdrop" role="presentation"><section className="personalization-modal personalization-modal-v2 vs-modal" role="dialog" aria-modal="true" aria-labelledby="personalization-title">
    {!started ? <>
      <div className="personalization-intro-mark">✦</div><span className="panel-kicker">Make V-SPACE yours</span><h2 id="personalization-title">A better plan starts with knowing your real life</h2><p className="personalization-intro-copy">In about 2 minutes, tell V-SPACE when your day happens, what already takes your time, and how you like to work. Then you will not have to repeat the same routine every time you ask for a plan.</p>
      <div className="personalization-value-strip"><div><strong>Less repeating</strong><span>Your normal routine becomes a starting point.</span></div><div><strong>More realistic plans</strong><span>Sleep, gym, university and breaks are respected.</span></div><div><strong>You stay in control</strong><span>What you say today always overrides your saved profile.</span></div></div>
      <div className="personalization-privacy-card"><strong>🔒 Your answers are optional and private to your V-SPACE account</strong><p>V-SPACE only reads the fields a feature needs. This profile is not sent to web-search providers, and you can review, change or clear it from Settings.</p></div>
      {error ? <p className="personalization-error">{error}</p> : null}
      <div className="personalization-modal-actions"><button type="button" className="secondary-button" onClick={() => void defer()} disabled={busy}>Maybe later</button><button type="button" className="primary-button" onClick={() => setStarted(true)}>Personalize my V-SPACE</button></div>
    </> : <>
      <header className="personalization-editor-heading"><div><span className="panel-kicker">Getting to know you</span><h2 id="personalization-title">One simple question at a time</h2></div><span>{step} / 7</span></header>
      <div className="personalization-progress"><span style={{ width: `${(step / 7) * 100}%` }} /></div>
      <OnboardingStep draft={draft} setDraft={setDraft} step={step} />
      <p className="personalization-optional-note">Nothing here is permanent. You can skip uncertain details, edit them later, and override any preference in a single plan.</p>
      {error ? <p className="personalization-error">{error}</p> : null}
      <div className="personalization-modal-actions"><button type="button" className="secondary-button" onClick={() => step === 1 ? setStarted(false) : setStep(step - 1)} disabled={busy}>Back</button><div>{step < 7 ? <button type="button" className="primary-button" onClick={() => setStep(step + 1)}>Continue</button> : <button type="button" className="primary-button" onClick={() => void save()} disabled={busy}>{busy ? "Saving…" : "Use these preferences"}</button>}</div></div>
    </>}
  </section></div>;
}

export function PersonalizationSettingsPanel() {
  const session = useSession();
  const queryClient = useQueryClient();
  const profileQuery = useQuery({ queryKey: ["personalization-profile"], queryFn: () => apiGet<{ personalization: PersonalizationProfile }>("/api/v1/personalization"), retry: false });
  const [draft, setDraft] = useState<Draft>(() => draftFrom());
  const [section, setSection] = useState(1);
  const [busy, setBusy] = useState(false);
  const [messageText, setMessageText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (profileQuery.data?.personalization) setDraft(draftFrom(profileQuery.data.personalization)); }, [profileQuery.data?.personalization.updated_at]);
  const profile = profileQuery.data?.personalization;
  const usage = useMemo(() => profile?.usage || {}, [profile?.updated_at]);

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["personalization-profile"] });
    await queryClient.invalidateQueries({ queryKey: ["session"] });
    await session.refetch();
  }
  async function save() {
    setBusy(true); setError(null); setMessageText(null);
    try { await apiPatch("/api/v1/personalization", payload(draft)); await refresh(); setMessageText("Your V-SPACE Profile has been updated."); }
    catch (err) { setError(message(err, "V-SPACE could not save your profile.")); }
    finally { setBusy(false); }
  }
  async function clear() {
    if (!window.confirm("Clear your optional V-SPACE personalization profile? Your projects, tasks, documents and account will not be affected.")) return;
    setBusy(true); setError(null); setMessageText(null);
    try { await apiDelete("/api/v1/personalization"); await refresh(); setMessageText("Your personalization answers were cleared. V-SPACE will use visible defaults until you add them again."); }
    catch (err) { setError(message(err, "V-SPACE could not clear your profile.")); }
    finally { setBusy(false); }
  }

  return <article className="experience-settings-panel personalization-settings-panel">
    <div className="experience-settings-copy"><span>Personalization</span><h2>Your V-SPACE Profile</h2><p>The routine V-SPACE can use to make planning feel personal. Explicit instructions always override these saved preferences.</p></div>
    {profileQuery.isPending ? <div className="personalization-settings-loading">Loading your private profile…</div> : profileQuery.isError ? <div className="personalization-error">V-SPACE could not load your personalization profile.</div> : <>
      <div className="personalization-settings-privacy"><strong>🔒 Private account data</strong><span>{profile?.privacy.message}</span><small>{profile?.answered_count || 0}/{profile?.total_questions || 7} personalization steps configured</small></div>
      <div className="personalization-settings-tabs">{[[1,"Life & routine"],[2,"Regular commitments"],[3,"Focus & energy"],[4,"Planning boundaries"]].map(([key,label]) => <button type="button" key={key} className={section === key ? "active" : ""} onClick={() => setSection(Number(key))}>{label}</button>)}</div>
      <SettingsEditor draft={draft} setDraft={setDraft} section={section} />
      <details className="personalization-data-use"><summary>Where will V-SPACE use this?</summary><div>{Object.entries(usage).map(([field, features]) => <div key={field}><strong>{field.replace(/_/g, " ")}</strong><span>{features.join(" · ")}</span></div>)}</div><p>Your life-context profile is not automatically injected into every AI request, and this V1 does not send it to web-search providers.</p></details>
      {messageText ? <div className="experience-settings-message success">{messageText}</div> : null}{error ? <div className="experience-settings-message error">{error}</div> : null}
      <div className="personalization-settings-actions"><button type="button" className="primary-button" onClick={() => void save()} disabled={busy}>{busy ? "Saving…" : "Save profile"}</button><button type="button" className="secondary-button" onClick={() => void clear()} disabled={busy}>Clear personalization</button></div>
    </>}
  </article>;
}
