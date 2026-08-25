import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent } from "react";
import { ApiError, apiGet, apiPost } from "../api/client";
import { navigate } from "../core/navigation";
import { PageState } from "../components/NativeUi";

type Task = {
  id: number;
  title: string;
  project: { id: number; title: string } | null;
  deadline: string | null;
  importance: string | null;
};

type Distraction = {
  id: number;
  content: string;
  captured_at: string | null;
  converted_task_id: number | null;
};

type Session = {
  id: number;
  task_id: number | null;
  task: { id: number; title: string; project?: { id: number; title: string } | null } | null;
  title: string;
  goal: string | null;
  planned_minutes: number;
  actual_minutes: number;
  elapsed_seconds: number;
  status: "running" | "paused" | "completed" | "cancelled" | string;
  distraction_count: number;
  goal_result: string | null;
  focus_rating: number | null;
  notes: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
  distractions: Distraction[];
};

type FocusData = {
  tasks: Task[];
  active_session: Session | null;
  elapsed_seconds: number;
  today_minutes: number;
};

type FocusInsights = {
  week_minutes: number;
  week_sessions: number;
  week_distractions: number;
  average_rating: number | null;
  daily_data: Array<{ label: string; date: string; minutes: number; height: number }>;
  project_data: Array<{ name: string; minutes: number }>;
  recent_sessions: Session[];
};

type Method = "sprint" | "deep" | "flow" | "custom";
type FocusTheme = "mist" | "sage" | "lavender" | "sand";
type FocusSound = "none" | "rain" | "brown" | "white";
type FocusSettings = {
  method: Method;
  minutes: number;
  breakMinutes: number;
  theme: FocusTheme;
  sound: FocusSound;
  volume: number;
  fullscreen: boolean;
  chime: boolean;
  wakeLock: boolean;
};

const STORAGE_PENDING = "lifeos-focus-pending-settings";
const STORAGE_DEFAULT = "lifeos-focus-default-settings";
const defaultSettings: FocusSettings = {
  method: "sprint",
  minutes: 25,
  breakMinutes: 5,
  theme: "mist",
  sound: "none",
  volume: 22,
  fullscreen: false,
  chime: true,
  wakeLock: false,
};

const methodNames: Record<Method, string> = {
  sprint: "Quick sprint",
  deep: "Deep work",
  flow: "Flow block",
  custom: "Custom session",
};
const themeNames: Record<FocusTheme, string> = {
  mist: "Mist",
  sage: "Sage",
  lavender: "Lavender",
  sand: "Sand",
};

function readSettings(key: string, fallback: FocusSettings = defaultSettings): FocusSettings {
  try {
    const saved = JSON.parse(localStorage.getItem(key) || "null") || {};
    return { ...fallback, ...saved };
  } catch {
    return { ...fallback };
  }
}

function writeSettings(key: string, value: FocusSettings) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable */ }
}

function formatTime(seconds: number) {
  const value = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(value / 60).toString().padStart(2, "0");
  const secs = (value % 60).toString().padStart(2, "0");
  return `${minutes}:${secs}`;
}

function formatDeadline(value: string | null) {
  if (!value) return "No deadline";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "No deadline";
  return date.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

function formatSessionDate(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function apiMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

type WakeLockSentinelLike = {
  release: () => Promise<void>;
  addEventListener: (name: "release", callback: () => void) => void;
};

type WakeNavigator = Navigator & {
  wakeLock?: { request: (type: "screen") => Promise<WakeLockSentinelLike> };
};

type WebkitWindow = Window & typeof globalThis & {
  webkitAudioContext?: typeof AudioContext;
};

export function FocusPage() {
  const query = useQuery({
    queryKey: ["focus"],
    queryFn: () => apiGet<FocusData>("/api/v1/focus"),
    refetchInterval: 30_000,
  });

  useEffect(() => {
    document.body.classList.add("focus-page-shell");
    return () => {
      document.body.classList.remove("focus-page-shell", "focus-immersive-active", "focus-panel-open", "focus-review-open");
    };
  }, []);

  if (query.isPending) return <PageState title="Opening Focus Studio" text="Preparing your focus workspace…" />;
  if (query.isError || !query.data) return <PageState title="Focus unavailable" text="LifeOS could not load Focus Mode." error retry={() => query.refetch()} />;

  return query.data.active_session
    ? <ActiveFocusSession data={query.data} refetch={() => query.refetch()} />
    : <FocusSetup data={query.data} refetch={() => query.refetch()} />;
}

function FocusSetup({ data, refetch }: { data: FocusData; refetch: () => Promise<unknown> }) {
  const [settings, setSettings] = useState<FocusSettings>(() => readSettings(STORAGE_DEFAULT));
  const [taskId, setTaskId] = useState<string>("");
  const [goal, setGoal] = useState("");
  const [error, setError] = useState<string | null>(null);

  const selectedTask = useMemo(() => data.tasks.find((task) => String(task.id) === taskId) || null, [data.tasks, taskId]);
  const soundText = settings.sound === "none" ? "Silent" : `${settings.sound.charAt(0).toUpperCase()}${settings.sound.slice(1)}`;
  const summary = `${settings.minutes}-minute ${methodNames[settings.method].toLowerCase()} · ${settings.breakMinutes}-minute break · ${themeNames[settings.theme]} · ${soundText}`;

  const startMutation = useMutation({
    mutationFn: (payload: { task_id: number | null; duration: number; goal: string }) => apiPost<{ session: Session }>("/api/v1/focus/start", payload),
    onError: (err) => setError(apiMessage(err, "The focus session could not be started.")),
    onSuccess: async () => {
      setError(null);
      await refetch();
    },
  });

  function chooseMethod(method: Method, minutes: number) {
    setSettings((current) => ({ ...current, method, minutes: method === "custom" ? current.minutes || minutes : minutes }));
  }

  async function submitStart(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextSettings = { ...settings, minutes: Math.min(180, Math.max(5, Number(settings.minutes) || 25)) };
    writeSettings(STORAGE_PENDING, nextSettings);
    writeSettings(STORAGE_DEFAULT, nextSettings);

    if (nextSettings.fullscreen && document.documentElement.requestFullscreen && !document.fullscreenElement) {
      try { await document.documentElement.requestFullscreen(); } catch { /* optional browser feature */ }
    }

    startMutation.mutate({
      task_id: taskId ? Number(taskId) : null,
      duration: nextSettings.minutes,
      goal,
    });
  }

  return (
    <section className="focus-studio-setup" id="focusSetupPage">
      <header className="focus-setup-header">
        <div>
          <span className="focus-setup-eyebrow">Focus studio</span>
          <h1>Set up the space, then do the work.</h1>
          <p>Useful options are available, but they stay organized around one clear starting point.</p>
        </div>
        <div className="focus-setup-header-actions">
          <div className="focus-today-pill"><span>Today</span><strong>{data.today_minutes} min</strong></div>
          <a href="/focus/insights" className="focus-insights-button">View insights</a>
        </div>
      </header>

      {error ? <div className="flash-message error" role="alert">{error}</div> : null}

      <form className="focus-setup-layout" id="focusSetupForm" onSubmit={submitStart}>
        <main className="focus-setup-main-card">
          <section className="focus-setup-section">
            <div className="focus-section-heading">
              <span>01</span>
              <div><h2>Choose the work</h2><p>Link a task or start a general session.</p></div>
            </div>

            <label className="focus-form-field">
              <span>Task</span>
              <select id="focusTaskSelect" value={taskId} onChange={(event) => setTaskId(event.target.value)}>
                <option value="">General focus session</option>
                {data.tasks.map((task) => (
                  <option key={task.id} value={task.id}>{task.title}{task.project ? ` — ${task.project.title}` : ""}</option>
                ))}
              </select>
            </label>

            <div className="focus-task-preview" id="focusTaskPreview">
              <div><span>Workspace</span><strong>{selectedTask?.project?.title || "General workspace"}</strong></div>
              <div><span>Priority</span><strong>{selectedTask ? `${selectedTask.importance || "Medium"} priority` : "Flexible"}</strong></div>
              <div><span>Deadline</span><strong>{formatDeadline(selectedTask?.deadline || null)}</strong></div>
            </div>

            <label className="focus-form-field">
              <span>Session outcome</span>
              <input value={goal} onChange={(event) => setGoal(event.target.value)} maxLength={500} placeholder="Example: Finish and test the reminder scheduler" />
              <small>One clear result is easier to focus on than a broad task.</small>
            </label>
          </section>

          <section className="focus-setup-section">
            <div className="focus-section-heading">
              <span>02</span>
              <div><h2>Choose a rhythm</h2><p>Select a ready method or set your own duration.</p></div>
            </div>

            <div className="focus-method-grid" id="focusMethodGrid">
              <button type="button" className={`focus-method-card ${settings.method === "sprint" ? "active" : ""}`} onClick={() => chooseMethod("sprint", 25)}><span>Quick sprint</span><strong>25 min</strong><small>Small, clear task</small></button>
              <button type="button" className={`focus-method-card ${settings.method === "deep" ? "active" : ""}`} onClick={() => chooseMethod("deep", 50)}><span>Deep work</span><strong>50 min</strong><small>Focused building</small></button>
              <button type="button" className={`focus-method-card ${settings.method === "flow" ? "active" : ""}`} onClick={() => chooseMethod("flow", 90)}><span>Flow block</span><strong>90 min</strong><small>Long creative work</small></button>
              <button type="button" className={`focus-method-card ${settings.method === "custom" ? "active" : ""}`} onClick={() => chooseMethod("custom", settings.method === "custom" ? settings.minutes : 40)}><span>Custom</span><strong>{settings.method === "custom" ? settings.minutes : 40} min</strong><small>Your own pace</small></button>
            </div>

            {settings.method === "custom" ? (
              <div className="focus-custom-duration" id="focusCustomDuration">
                <label><span>Custom focus duration</span><input type="number" min={5} max={180} value={settings.minutes} onChange={(event) => setSettings((current) => ({ ...current, method: "custom", minutes: Math.min(180, Math.max(5, Number(event.target.value) || 5)) }))} /></label>
              </div>
            ) : null}
          </section>
        </main>

        <aside className="focus-session-tools-card">
          <div className="focus-tools-card-heading"><span>Optional</span><h2>Session tools</h2><p>Set the environment once. These controls stay out of the way after you start.</p></div>

          <section className="focus-tool-setting">
            <div><h3>Break length</h3><p>Used by the break button during the session.</p></div>
            <div className="focus-segmented-control" id="setupBreakOptions">
              {[5, 10, 15].map((minutes) => <button key={minutes} type="button" className={settings.breakMinutes === minutes ? "active" : ""} onClick={() => setSettings((current) => ({ ...current, breakMinutes: minutes }))}>{minutes} min</button>)}
            </div>
          </section>

          <section className="focus-tool-setting">
            <div><h3>Workspace color</h3><p>Choose the active timer palette. The Focus dashboard follows your LifeOS theme.</p></div>
            <div className="focus-theme-options" id="setupThemeOptions">
              {(["mist", "sage", "lavender", "sand"] as FocusTheme[]).map((theme) => (
                <button key={theme} type="button" className={settings.theme === theme ? "active" : ""} onClick={() => setSettings((current) => ({ ...current, theme }))}><i className={`theme-${theme}`} /><span>{themeNames[theme]}</span></button>
              ))}
            </div>
          </section>

          <section className="focus-tool-setting">
            <div><h3>Ambient sound</h3><p>Start silent or choose a generated sound.</p></div>
            <div className="focus-sound-options" id="setupSoundOptions">
              {(["none", "rain", "brown", "white"] as FocusSound[]).map((sound) => <button key={sound} type="button" className={settings.sound === sound ? "active" : ""} onClick={() => setSettings((current) => ({ ...current, sound }))}>{sound === "none" ? "None" : sound === "brown" ? "Brown" : sound === "white" ? "White" : "Rain"}</button>)}
            </div>
          </section>

          <section className="focus-tool-toggles">
            <label><input type="checkbox" checked={settings.fullscreen} onChange={(event) => setSettings((current) => ({ ...current, fullscreen: event.target.checked }))} /><span><strong>Start fullscreen</strong><small>Hide browser distractions when supported.</small></span></label>
            <label><input type="checkbox" checked={settings.chime} onChange={(event) => setSettings((current) => ({ ...current, chime: event.target.checked }))} /><span><strong>Completion chime</strong><small>Play a gentle tone when time ends.</small></span></label>
            <label><input type="checkbox" checked={settings.wakeLock} onChange={(event) => setSettings((current) => ({ ...current, wakeLock: event.target.checked }))} /><span><strong>Keep screen awake</strong><small>Prevent the screen from sleeping.</small></span></label>
          </section>
        </aside>

        <footer className="focus-start-bar">
          <div><span>Ready session</span><strong id="focusSetupSummary">{summary}</strong></div>
          <button type="submit" className="focus-start-button" disabled={startMutation.isPending}><span>{startMutation.isPending ? "Starting…" : "Start focus"}</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 18 6-6-6-6-1.4 1.4 4.6 4.6-4.6 4.6L9 18Z" /></svg></button>
        </footer>
      </form>
    </section>
  );
}

function ActiveFocusSession({ data, refetch }: { data: FocusData; refetch: () => Promise<unknown> }) {
  const session = data.active_session!;
  const sessionKey = `lifeos-focus-session-${session.id}`;
  const [settings, setSettings] = useState<FocusSettings>(() => {
    const sessionSaved = readSettings(sessionKey, readSettings(STORAGE_DEFAULT));
    if (localStorage.getItem(sessionKey)) return sessionSaved;
    const pending = readSettings(STORAGE_PENDING, sessionSaved);
    writeSettings(sessionKey, pending);
    try { localStorage.removeItem(STORAGE_PENDING); } catch { /* ignore */ }
    return pending;
  });
  const [elapsed, setElapsed] = useState(data.elapsed_seconds || 0);
  const [error, setError] = useState<string | null>(null);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [thoughtsOpen, setThoughtsOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [completionOpen, setCompletionOpen] = useState(false);
  const [breakOpen, setBreakOpen] = useState(false);
  const [breakRemaining, setBreakRemaining] = useState(Math.max(1, settings.breakMinutes) * 60);
  const [thought, setThought] = useState("");
  const [thoughtFeedback, setThoughtFeedback] = useState("");
  const [soundPlaying, setSoundPlaying] = useState(false);
  const [wakeStatus, setWakeStatus] = useState<"Off" | "On" | "Unavailable">("Off");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const completionHandled = useRef(false);
  const breakFinished = useRef(false);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const audioGainRef = useRef<GainNode | null>(null);
  const wakeLockRef = useRef<WakeLockSentinelLike | null>(null);

  const linkedTask = useMemo(() => data.tasks.find((task) => task.id === session.task_id) || null, [data.tasks, session.task_id]);
  const taskProject = session.task?.project?.title || linkedTask?.project?.title || null;
  const totalSeconds = Math.max(1, session.planned_minutes) * 60;
  const remaining = totalSeconds - elapsed;
  const timerText = formatTime(Math.abs(remaining));
  const timerCaption = remaining >= 0 ? (session.status === "paused" ? "paused" : "remaining") : "overtime";
  const progressDegrees = Math.min(1, Math.max(0, elapsed / totalSeconds)) * 360;

  useEffect(() => {
    document.body.classList.add("focus-page-shell", "focus-immersive-active");
    return () => document.body.classList.remove("focus-immersive-active", "focus-panel-open", "focus-review-open");
  }, []);

  useEffect(() => setElapsed(data.elapsed_seconds || 0), [data.elapsed_seconds, session.id]);
  useEffect(() => {
    if (session.status !== "running") return;
    const interval = window.setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => window.clearInterval(interval);
  }, [session.status, session.id]);

  useEffect(() => {
    document.title = `${timerText} · LifeOS Focus`;
    return () => { document.title = "LifeOS AI"; };
  }, [timerText]);

  useEffect(() => {
    if (elapsed < totalSeconds) completionHandled.current = false;
  }, [elapsed, totalSeconds]);

  useEffect(() => {
    if (session.status !== "running" || elapsed < totalSeconds || completionHandled.current) return;
    completionHandled.current = true;
    void handleTimerComplete();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [elapsed, totalSeconds, session.status]);

  useEffect(() => {
    writeSettings(sessionKey, settings);
    writeSettings(STORAGE_DEFAULT, settings);
  }, [settings, sessionKey]);

  useEffect(() => {
    document.body.classList.toggle("focus-panel-open", toolsOpen || thoughtsOpen);
    document.body.classList.toggle("focus-review-open", reviewOpen);
  }, [toolsOpen, thoughtsOpen, reviewOpen]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (reviewOpen) setReviewOpen(false);
      else if (thoughtsOpen) setThoughtsOpen(false);
      else if (toolsOpen) setToolsOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [reviewOpen, thoughtsOpen, toolsOpen]);

  useEffect(() => {
    if (!breakOpen || breakRemaining <= 0) return;
    const interval = window.setInterval(() => setBreakRemaining((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(interval);
  }, [breakOpen, breakRemaining]);

  useEffect(() => {
    if (!breakOpen || breakRemaining !== 0 || breakFinished.current) return;
    breakFinished.current = true;
    void playChime();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [breakOpen, breakRemaining]);

  useEffect(() => {
    if (!settings.wakeLock) return;
    void requestWakeLock();
    return () => { void wakeLockRef.current?.release().catch(() => {}); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.id]);

  useEffect(() => () => {
    stopAmbientSound();
    void wakeLockRef.current?.release().catch(() => {});
  }, []);

  async function runAction<T>(name: string, action: () => Promise<T>, fallback: string): Promise<T | null> {
    setBusyAction(name);
    setError(null);
    try { return await action(); }
    catch (err) { setError(apiMessage(err, fallback)); return null; }
    finally { setBusyAction(null); }
  }

  async function pauseSession() {
    if (session.status !== "running") return true;
    const result = await runAction("pause", () => apiPost<{ session: Session }>(`/api/v1/focus/${session.id}/pause`), "Could not pause this session.");
    if (!result) return false;
    if (typeof result.session.elapsed_seconds === "number") setElapsed(result.session.elapsed_seconds);
    await refetch();
    return true;
  }

  async function resumeSession() {
    if (session.status !== "paused") return true;
    const result = await runAction("resume", () => apiPost<{ session: Session }>(`/api/v1/focus/${session.id}/resume`), "Could not resume this session.");
    if (!result) return false;
    await refetch();
    return true;
  }

  async function extendSession() {
    const result = await runAction("extend", () => apiPost<{ session: Session }>(`/api/v1/focus/${session.id}/extend`), "Could not extend this session.");
    if (!result) return;
    await refetch();
  }

  async function beginReview() {
    const result = await runAction("review", () => apiPost<{ session: Session; review_requested: boolean }>(`/api/v1/focus/${session.id}/review`), "Could not open the focus review.");
    if (!result) return;
    setCompletionOpen(false);
    await refetch();
    setReviewOpen(true);
  }

  async function cancelSession() {
    if (!window.confirm("Leave this session?\n\nThe elapsed time will be kept, but the session will be marked as cancelled.")) return;
    const result = await runAction("cancel", () => apiPost<{ session: Session }>(`/api/v1/focus/${session.id}/cancel`), "The focus session could not be ended.");
    if (!result) return;
    stopAmbientSound();
    await refetch();
  }

  async function handleTimerComplete() {
    try { await pauseSession(); } catch { /* keep completion UI usable */ }
    await playChime();
    setCompletionOpen(true);
  }

  function buildNoiseBuffer(context: AudioContext, type: "brown" | "white") {
    const seconds = 3;
    const length = context.sampleRate * seconds;
    const buffer = context.createBuffer(1, length, context.sampleRate);
    const channel = buffer.getChannelData(0);
    let last = 0;
    for (let index = 0; index < length; index += 1) {
      const white = Math.random() * 2 - 1;
      if (type === "brown") {
        last = (last + 0.02 * white) / 1.02;
        channel[index] = last * 3.5;
      } else channel[index] = white;
    }
    return buffer;
  }

  function stopAmbientSound() {
    try { audioSourceRef.current?.stop(); } catch { /* already stopped */ }
    try { audioSourceRef.current?.disconnect(); } catch { /* ignore */ }
    try { audioGainRef.current?.disconnect(); } catch { /* ignore */ }
    audioSourceRef.current = null;
    audioGainRef.current = null;
    setSoundPlaying(false);
  }

  async function startAmbientSound(soundOverride?: FocusSound) {
    const selectedSound = soundOverride ?? settings.sound;
    if (selectedSound === "none") { setToolsOpen(true); return; }
    stopAmbientSound();
    const AudioCtor = window.AudioContext || (window as WebkitWindow).webkitAudioContext;
    if (!AudioCtor) return;
    const context = audioContextRef.current || new AudioCtor();
    audioContextRef.current = context;
    if (context.state === "suspended") await context.resume();

    const source = context.createBufferSource();
    source.buffer = buildNoiseBuffer(context, selectedSound === "brown" ? "brown" : "white");
    source.loop = true;
    const gain = context.createGain();
    gain.gain.value = Math.max(0, Math.min(1, settings.volume / 100));

    if (selectedSound === "rain") {
      const highPass = context.createBiquadFilter();
      highPass.type = "highpass"; highPass.frequency.value = 750;
      const lowPass = context.createBiquadFilter();
      lowPass.type = "lowpass"; lowPass.frequency.value = 6500;
      source.connect(highPass).connect(lowPass).connect(gain).connect(context.destination);
    } else source.connect(gain).connect(context.destination);

    source.start();
    audioSourceRef.current = source;
    audioGainRef.current = gain;
    setSoundPlaying(true);
  }

  async function playChime() {
    if (!settings.chime) return;
    const AudioCtor = window.AudioContext || (window as WebkitWindow).webkitAudioContext;
    if (!AudioCtor) return;
    const context = audioContextRef.current || new AudioCtor();
    audioContextRef.current = context;
    if (context.state === "suspended") await context.resume();
    const now = context.currentTime;
    [523.25, 659.25].forEach((frequency, index) => {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.frequency.value = frequency;
      oscillator.type = "sine";
      gain.gain.setValueAtTime(0, now + index * 0.16);
      gain.gain.linearRampToValueAtTime(0.09, now + index * 0.16 + 0.03);
      gain.gain.exponentialRampToValueAtTime(0.001, now + index * 0.16 + 0.55);
      oscillator.connect(gain).connect(context.destination);
      oscillator.start(now + index * 0.16);
      oscillator.stop(now + index * 0.16 + 0.6);
    });
  }

  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch { /* unsupported or denied */ }
  }

  async function requestWakeLock() {
    const wake = (navigator as WakeNavigator).wakeLock;
    if (!wake) { setWakeStatus("Unavailable"); return false; }
    try {
      const lock = await wake.request("screen");
      wakeLockRef.current = lock;
      setWakeStatus("On");
      lock.addEventListener("release", () => {
        wakeLockRef.current = null;
        setWakeStatus("Off");
      });
      return true;
    } catch {
      setWakeStatus("Unavailable");
      return false;
    }
  }

  async function toggleWakeLock() {
    if (wakeLockRef.current) {
      try { await wakeLockRef.current.release(); } catch { /* ignore */ }
      wakeLockRef.current = null;
      setWakeStatus("Off");
      setSettings((current) => ({ ...current, wakeLock: false }));
      return;
    }
    const active = await requestWakeLock();
    setSettings((current) => ({ ...current, wakeLock: active }));
  }

  async function submitThought(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = thought.trim();
    if (!content) return;
    const result = await runAction("thought", () => apiPost<{ item: Distraction }>(`/api/v1/focus/${session.id}/distractions`, { content }), "Could not save thought.");
    if (!result) return;
    setThought("");
    setThoughtFeedback("Saved. Your mind can let it go.");
    await refetch();
  }

  async function convertThought(id: number) {
    const result = await runAction(`convert-${id}`, () => apiPost(`/api/v1/focus/distractions/${id}/convert`), "Could not create task.");
    if (result) await refetch();
  }

  async function showBreak() {
    try { await pauseSession(); } catch { /* keep local break usable */ }
    setCompletionOpen(false);
    breakFinished.current = false;
    setBreakRemaining(Math.max(1, settings.breakMinutes) * 60);
    setBreakOpen(true);
  }

  async function endBreak() {
    setBreakOpen(false);
    await resumeSession();
  }

  const soundLabel = settings.sound === "none" ? "Choose sound" : soundPlaying ? `${settings.sound} on` : `Start ${settings.sound}`;

  return (
    <>
      <section className={`focus-calm-session ${remaining < 0 ? "is-overtime" : ""}`} id="focusSession" data-focus-theme={settings.theme}>
        <header className="focus-session-topbar">
          <div className="focus-session-identity">
            <span className="focus-session-logo">L</span>
            <div><strong>LifeOS Focus</strong><span>{session.task ? `${session.task.title}${taskProject ? ` · ${taskProject}` : ""}` : "General focus session"}</span></div>
          </div>
          <div className="focus-session-top-actions">
            <button type="button" className="focus-icon-button" onClick={() => setToolsOpen(true)} aria-label="Open focus tools" title="Focus tools"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm7.43-2.53c.04-.32.07-.65.07-.97s-.03-.65-.08-.97l2.11-1.65-2-3.46-2.49 1a7.55 7.55 0 0 0-1.68-.97L15 3.27h-4l-.37 2.68c-.6.24-1.16.56-1.68.97l-2.49-1-2 3.46 2.11 1.65c-.04.32-.07.65-.07.97s.03.65.08.97l-2.11 1.65 2 3.46 2.49-1c.52.41 1.08.73 1.68.97l.36 2.68h4l.37-2.68c.6-.24 1.16-.56 1.68-.97l2.49 1 2-3.46-2.11-1.65Z" /></svg></button>
            <button type="button" className="focus-icon-button" onClick={() => void toggleFullscreen()} aria-label="Toggle fullscreen" title="Fullscreen"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9V4h5v2H6v3H4Zm11-5h5v5h-2V6h-3V4ZM6 15v3h3v2H4v-5h2Zm12 3v-3h2v5h-5v-2h3Z" /></svg></button>
          </div>
        </header>

        <main className="focus-session-main">
          <div className="focus-session-labels"><span className="focus-phase-pill">Focus session</span><span className="focus-method-pill">{methodNames[settings.method] || "Focus session"}</span></div>
          <p className="focus-session-goal-label">Current outcome</p>
          <h1 className="focus-session-goal">{session.goal || "Make meaningful progress on this task."}</h1>

          <div className="focus-timer-ring" aria-label="Focus timer" style={{ "--timer-progress": `${progressDegrees}deg` } as CSSProperties}>
            <div className="focus-timer-ring-inner"><strong>{timerText}</strong><span>{timerCaption}</span></div>
          </div>

          {error ? <div className="focus-inline-error" role="alert">{error}</div> : null}

          <div className="focus-session-controls">
            <button type="button" className="focus-action-button secondary" disabled={busyAction === "pause" || busyAction === "resume"} onClick={() => void (session.status === "paused" ? resumeSession() : pauseSession())}><svg viewBox="0 0 24 24" aria-hidden="true"><path d={session.status === "paused" ? "M8 5v14l11-7L8 5Z" : "M7 5h4v14H7V5Zm6 0h4v14h-4V5Z"} /></svg><span>{session.status === "paused" ? "Resume" : "Pause"}</span></button>
            <button type="button" className="focus-action-button quiet" disabled={busyAction === "extend"} onClick={() => void extendSession()}>{busyAction === "extend" ? "Adding…" : "+5 minutes"}</button>
            <button type="button" className="focus-action-button primary" disabled={busyAction === "review"} onClick={() => void beginReview()}>End session</button>
          </div>

          <nav className="focus-tool-dock" aria-label="Focus session tools">
            <button type="button" onClick={() => void showBreak()}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4h10v2h-1v5a4 4 0 0 1-3 3.87V18h3v2H8v-2h3v-3.13A4 4 0 0 1 8 11V6H7V4Zm3 2v5a2 2 0 1 0 4 0V6h-4Z" /></svg><span>Take a break</span></button>
            <button type="button" onClick={() => setThoughtsOpen(true)}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h16v12H7l-3 3V4Zm3 4v2h10V8H7Zm0 4v2h7v-2H7Z" /></svg><span>Park a thought</span>{session.distraction_count ? <b>{session.distraction_count}</b> : null}</button>
            <button type="button" onClick={() => void (settings.sound === "none" ? Promise.resolve(setToolsOpen(true)) : soundPlaying ? Promise.resolve(stopAmbientSound()) : startAmbientSound())}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10v4h4l5 4V6L8 10H4Zm12.5 2a4.5 4.5 0 0 0-2.5-4.03v8.06A4.5 4.5 0 0 0 16.5 12Zm-2.5-8.48v2.06A7 7 0 0 1 14 18.42v2.06A9 9 0 0 0 14 3.52Z" /></svg><span>{soundLabel}</span></button>
          </nav>
        </main>

        <div className="focus-session-exit"><button type="button" disabled={busyAction === "cancel"} onClick={() => void cancelSession()}>Exit without completing</button></div>
      </section>

      <div className="focus-side-backdrop" hidden={!toolsOpen} onClick={() => setToolsOpen(false)} />
      <aside className={`focus-side-panel ${toolsOpen ? "open" : ""}`} aria-hidden={!toolsOpen}>
        <header><div><span>Session controls</span><h2>Focus tools</h2></div><button type="button" className="focus-panel-close" onClick={() => setToolsOpen(false)} aria-label="Close tools">×</button></header>
        <section className="focus-tool-section">
          <div className="focus-tool-heading"><h3>Background</h3><p>Choose a calmer workspace without changing the whole app theme.</p></div>
          <div className="focus-theme-options">
            {(["mist", "sage", "lavender", "sand"] as FocusTheme[]).map((theme) => <button key={theme} type="button" className={settings.theme === theme ? "active" : ""} onClick={() => setSettings((current) => ({ ...current, theme }))}><i className={`theme-${theme}`} /><span>{themeNames[theme]}</span></button>)}
          </div>
        </section>
        <section className="focus-tool-section">
          <div className="focus-tool-heading"><h3>Ambient sound</h3><p>Generated in the browser. No external audio files are required.</p></div>
          <div className="focus-sound-options">
            {(["none", "rain", "brown", "white"] as FocusSound[]).map((sound) => <button key={sound} type="button" className={settings.sound === sound ? "active" : ""} onClick={() => { setSettings((current) => ({ ...current, sound })); if (sound === "none") stopAmbientSound(); else void startAmbientSound(sound); }}>{sound === "none" ? "None" : sound === "brown" ? "Brown noise" : sound === "white" ? "White noise" : "Rain"}</button>)}
          </div>
          <label className="focus-volume-control"><span>Volume</span><input type="range" min={0} max={100} value={settings.volume} onChange={(event) => { const volume = Number(event.target.value); setSettings((current) => ({ ...current, volume })); if (audioGainRef.current) audioGainRef.current.gain.value = volume / 100; }} /></label>
        </section>
        <section className="focus-tool-section compact"><button type="button" className="focus-wide-tool-button" onClick={() => void toggleWakeLock()}><span>Keep screen awake</span><small>{wakeStatus}</small></button></section>
      </aside>

      <div className="focus-side-backdrop" hidden={!thoughtsOpen} onClick={() => setThoughtsOpen(false)} />
      <aside className={`focus-side-panel ${thoughtsOpen ? "open" : ""}`} aria-hidden={!thoughtsOpen}>
        <header><div><span>Distraction inbox</span><h2>Park it and return</h2></div><button type="button" className="focus-panel-close" onClick={() => setThoughtsOpen(false)} aria-label="Close thoughts">×</button></header>
        <form className="focus-thought-compose" onSubmit={submitThought}>
          <label htmlFor="parkThoughtInput">What is pulling your attention?</label>
          <textarea id="parkThoughtInput" maxLength={500} rows={3} value={thought} onChange={(event) => setThought(event.target.value)} placeholder="Write it here so you do not have to hold it in your mind." />
          <div><small aria-live="polite">{thoughtFeedback}</small><button type="submit" disabled={busyAction === "thought"}>Park thought</button></div>
        </form>
        <div className="focus-thought-list">
          {session.distractions.length ? session.distractions.map((item) => <article key={item.id}><p>{item.content}</p><div><span>{item.captured_at ? new Date(item.captured_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}</span>{item.converted_task_id ? <small>Added to tasks</small> : <button type="button" className="convert-thought-button" disabled={busyAction === `convert-${item.id}`} onClick={() => void convertThought(item.id)}>Convert to task</button>}</div></article>) : <p className="focus-empty-thoughts">Nothing parked yet.</p>}
        </div>
      </aside>

      <div className="focus-break-overlay" hidden={!breakOpen}>
        <section className="focus-break-card"><span className="focus-break-icon">☕</span><p>Reset, do not scroll.</p><strong>{breakRemaining > 0 ? formatTime(breakRemaining) : "Ready"}</strong><div className="focus-break-suggestions"><span>Look away from the screen</span><span>Stand and stretch</span><span>Drink water</span></div><div className="focus-break-actions"><button type="button" className="focus-action-button secondary" onClick={() => void endBreak()}>Skip break</button><button type="button" className="focus-action-button primary" onClick={() => void endBreak()}>Resume focus</button></div></section>
      </div>

      <div className="focus-complete-sheet" hidden={!completionOpen}>
        <section><span>Focus block complete</span><h2>You reached your planned time.</h2><p>Choose what helps you continue intentionally.</p><div><button type="button" className="focus-action-button secondary" onClick={() => void showBreak()}>Take a break</button><button type="button" className="focus-action-button quiet" onClick={() => { setCompletionOpen(false); void resumeSession(); }}>Continue working</button><button type="button" className="focus-action-button primary" onClick={() => void beginReview()}>Review session</button></div></section>
      </div>

      <ReviewModal session={session} open={reviewOpen} busy={busyAction === "finish"} onClose={() => setReviewOpen(false)} onFinish={async (payload, destination) => {
        const result = await runAction("finish", () => apiPost<{ session: Session }>(`/api/v1/focus/${session.id}/finish`, payload), "The focus session could not be saved.");
        if (!result) return;
        stopAmbientSound();
        setReviewOpen(false);
        await refetch();
        if (destination === "dashboard") navigate("/dashboard", true);
      }} />
    </>
  );
}

function ReviewModal({ session, open, busy, onClose, onFinish }: {
  session: Session;
  open: boolean;
  busy: boolean;
  onClose: () => void;
  onFinish: (payload: { notes: string; goal_result: string | null; focus_rating: number | null; complete_task: boolean }, destination: "focus" | "dashboard") => Promise<void>;
}) {
  const [goalResult, setGoalResult] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [rating, setRating] = useState("");
  const [completeTask, setCompleteTask] = useState(false);

  useEffect(() => {
    if (!open) return;
    setGoalResult(null); setNotes(""); setRating(""); setCompleteTask(false);
  }, [open, session.id]);

  if (!open) return null;
  const payload = { notes, goal_result: goalResult, focus_rating: rating ? Number(rating) : null, complete_task: completeTask };

  return <div className="focus-review-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="focus-review-card" role="dialog" aria-modal="true" aria-labelledby="focusReviewTitle">
      <span className="review-check">✓</span><p className="review-kicker">Session complete</p><h2 id="focusReviewTitle">Close the loop</h2>
      {session.goal ? <fieldset className="review-choice-group"><legend>Did you achieve the outcome?</legend>{[["full", "Yes"], ["partial", "Partly"], ["not_yet", "Not yet"]].map(([value, label]) => <label key={value}><input type="radio" name="goal_result" value={value} checked={goalResult === value} onChange={() => setGoalResult(value)} /><span>{label}</span></label>)}</fieldset> : null}
      <label className="review-field"><span>Session note <small>(optional)</small></span><textarea rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="What moved forward, and what should happen next?" /></label>
      <label className="review-field compact"><span>Focus quality <small>(optional)</small></span><select value={rating} onChange={(event) => setRating(event.target.value)}><option value="">Not rated</option><option value="5">5 — Fully focused</option><option value="4">4 — Focused</option><option value="3">3 — Mixed</option><option value="2">2 — Distracted</option><option value="1">1 — Very distracted</option></select></label>
      {session.task ? <label className="review-task-check"><input type="checkbox" checked={completeTask} onChange={(event) => setCompleteTask(event.target.checked)} /><span>Mark “{session.task.title}” as completed</span></label> : null}
      <div className="review-actions review-actions-complete"><button type="button" className="focus-action-button quiet review-return-button" onClick={onClose}>Return to session</button><button type="button" className="focus-action-button secondary" disabled={busy} onClick={() => void onFinish(payload, "focus")}>Save &amp; Focus Home</button><button type="button" className="focus-action-button primary review-dashboard-button" disabled={busy} onClick={() => void onFinish(payload, "dashboard")}>{busy ? "Saving…" : "Save & Dashboard"}</button></div>
    </section>
  </div>;
}

export function FocusInsightsPage() {
  const query = useQuery({ queryKey: ["focus-insights"], queryFn: () => apiGet<FocusInsights>("/api/v1/focus/insights") });
  useEffect(() => {
    document.body.classList.add("focus-page-shell");
    return () => document.body.classList.remove("focus-page-shell");
  }, []);
  if (query.isPending) return <PageState title="Loading insights" text="Reviewing your focus history…" />;
  if (query.isError || !query.data) return <PageState title="Insights unavailable" text="Could not load focus insights." error retry={() => query.refetch()} />;
  const data = query.data;

  return <section className="focus-insights-page">
    <header className="focus-insights-header"><div><span className="focus-setup-eyebrow">Focus insights</span><h1>See the pattern, not the noise.</h1><p>Your focus activity is kept here, away from the active timer.</p></div><a href="/focus" className="focus-insights-button">Start focus</a></header>
    <section className="focus-insight-summary"><article><strong>{data.week_minutes}</strong><span>minutes this week</span></article><article><strong>{data.week_sessions}</strong><span>completed sessions</span></article><article><strong>{data.average_rating ?? "—"}</strong><span>average focus rating</span></article><article><strong>{data.week_distractions}</strong><span>parked thoughts</span></article></section>
    <section className="focus-insight-panel"><div className="focus-panel-heading"><div><span>Last 7 days</span><h2>Focused minutes</h2></div></div><div className="focus-week-bars" aria-label="Focused minutes in the last seven days">{data.daily_data.map((day) => <div className="focus-day-column" title={`${day.date}: ${day.minutes} minutes`} key={day.date}><div className="focus-bar-track"><span style={{ height: `${day.height}%` }} /></div><strong>{day.minutes}</strong><small>{day.label}</small></div>)}</div></section>
    <div className="focus-insights-grid">
      <section className="focus-insight-panel"><div className="focus-panel-heading"><div><span>Allocation</span><h2>Time by project</h2></div></div>{data.project_data.length ? <div className="focus-project-list">{data.project_data.map((project) => <div key={project.name}><span>{project.name}</span><strong>{project.minutes} min</strong></div>)}</div> : <p className="focus-empty-copy">Complete a focus session to see project allocation.</p>}</section>
      <section className="focus-insight-panel"><div className="focus-panel-heading"><div><span>History</span><h2>Recent sessions</h2></div></div>{data.recent_sessions.length ? <div className="focus-recent-list">{data.recent_sessions.map((item) => <article key={item.id}><div><strong>{item.title}</strong><span>{formatSessionDate(item.completed_at || item.created_at)}</span></div><div><strong>{item.actual_minutes || 0} min</strong>{item.focus_rating ? <span>{item.focus_rating}/5 focus</span> : null}</div></article>)}</div> : <p className="focus-empty-copy">No completed sessions yet.</p>}</section>
    </div>
  </section>;
}
