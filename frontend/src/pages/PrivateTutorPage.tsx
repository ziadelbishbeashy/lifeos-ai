import { useMemo, useState, type CSSProperties, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ApiError, apiGet, apiPost } from "../api/client";
import type { LearningModuleDetail } from "../api/types";
import { BrandMark, Icon, PageSkeleton } from "../components/VSpaceUi";


type TutorMode = "explain" | "summarize" | "quiz" | "practice" | "flashcards";
type TutorDifficulty = "beginner" | "intermediate" | "advanced";
type TutorSource = {
  source_id: number;
  document_id: number;
  filename: string;
  page?: number | string | null;
  section?: string | null;
  content_type?: string | null;
  evidence?: string | null;
};
type TutorQuestion = {
  id: string;
  prompt: string;
  options?: string[];
  hint?: string;
  solution?: string;
  topic?: string;
  source_ids: number[];
};
type TutorContent = {
  title: string;
  body_markdown?: string;
  key_points?: Array<{ text: string; source_ids: number[] }>;
  check_questions?: string[];
  source_ids?: number[];
  instructions?: string;
  questions?: TutorQuestion[];
  study_tip?: string;
  cards?: Array<{ id: string; front: string; back: string; source_ids: number[] }>;
};
type TutorSession = {
  id: number;
  module_id: number;
  module_title: string;
  lecture_id: number | null;
  lecture_title: string | null;
  mode: TutorMode;
  difficulty: TutorDifficulty;
  topic: string | null;
  request_text: string | null;
  content: TutorContent;
  sources: TutorSource[];
  status: string;
  score: { correct: number | null; total: number | null; percentage: number | null };
  weak_areas: string[];
  created_at: string | null;
};
type TutorHome = {
  modules: LearningModuleDetail[];
  recent_sessions: TutorSession[];
};
type TutorGradeResult = {
  correct: number;
  total: number;
  percentage: number;
  weak_areas: string[];
  results: Array<{
    id: string;
    prompt: string;
    selected_index: number | null;
    correct_index: number;
    correct: boolean;
    correct_answer: string | null;
    explanation: string;
    topic: string;
    source_ids: number[];
  }>;
};

const modeMeta: Array<{ value: TutorMode; label: string; description: string }> = [
  { value: "explain", label: "Explain", description: "Learn a concept step by step" },
  { value: "summarize", label: "Summarize", description: "Turn material into exam-ready notes" },
  { value: "quiz", label: "Quiz me", description: "Test yourself and find weak areas" },
  { value: "practice", label: "Practice", description: "Work through guided questions" },
  { value: "flashcards", label: "Flashcards", description: "Build fast active-recall revision" },
];

function apiMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

function formatTime(value: string | null) {
  if (!value) return "";
  const parsed = new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`);
  if (Number.isNaN(parsed.getTime())) return "";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(parsed);
}

function TutorMarkdown({ value }: { value: string }) {
  const lines = value.replace(/\r/g, "").split("\n");
  const nodes: ReactNode[] = [];
  let bullets: string[] = [];
  const flushBullets = () => {
    if (!bullets.length) return;
    nodes.push(<ul key={`list-${nodes.length}`}>{bullets.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>);
    bullets = [];
  };
  lines.forEach((raw, index) => {
    const line = raw.trim();
    if (!line) { flushBullets(); return; }
    if (/^[-*]\s+/.test(line)) { bullets.push(line.replace(/^[-*]\s+/, "")); return; }
    flushBullets();
    if (line.startsWith("### ")) nodes.push(<h4 key={index}>{line.slice(4)}</h4>);
    else if (line.startsWith("## ")) nodes.push(<h3 key={index}>{line.slice(3)}</h3>);
    else if (line.startsWith("# ")) nodes.push(<h3 key={index}>{line.slice(2)}</h3>);
    else nodes.push(<p key={index}>{line}</p>);
  });
  flushBullets();
  return <div className="tutor-markdown">{nodes}</div>;
}

function SourceChips({ ids, sources }: { ids?: number[]; sources: TutorSource[] }) {
  if (!ids?.length) return null;
  return <div className="tutor-source-chips">{ids.map(id => {
    const source = sources.find(item => item.source_id === id);
    return <span key={id} title={source?.filename || `Source ${id}`}>S{id}</span>;
  })}</div>;
}

function ScoreRing({ percentage }: { percentage: number }) {
  const bounded = Math.max(0, Math.min(100, percentage));
  return <div className="tutor-score-ring" style={{ "--score": `${bounded * 3.6}deg` } as CSSProperties}><div><strong>{bounded}%</strong><span>score</span></div></div>;
}

export function PrivateTutorPage() {
  const [moduleId, setModuleId] = useState("");
  const [lectureId, setLectureId] = useState("");
  const [mode, setMode] = useState<TutorMode>("explain");
  const [difficulty, setDifficulty] = useState<TutorDifficulty>("intermediate");
  const [topic, setTopic] = useState("");
  const [requestText, setRequestText] = useState("");
  const [questionCount, setQuestionCount] = useState(5);
  const [active, setActive] = useState<TutorSession | null>(null);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [grade, setGrade] = useState<TutorGradeResult | null>(null);
  const [revealed, setRevealed] = useState<Record<string, "hint" | "solution" | "back">>({});
  const [error, setError] = useState<string | null>(null);

  const homeQuery = useQuery({
    queryKey: ["private-tutor"],
    queryFn: () => apiGet<TutorHome>("/api/v1/tutor"),
  });

  const selectedModule = useMemo(() => homeQuery.data?.modules.find(item => item.id === Number(moduleId)) || null, [homeQuery.data?.modules, moduleId]);
  const lectures = selectedModule?.lectures || [];

  const createMutation = useMutation({
    mutationFn: () => apiPost<{ session: TutorSession }>("/api/v1/tutor/sessions", {
      module_id: Number(moduleId),
      lecture_id: lectureId ? Number(lectureId) : null,
      mode,
      difficulty,
      topic: topic.trim() || null,
      request_text: requestText.trim() || null,
      question_count: questionCount,
    }),
    onSuccess: ({ session }) => {
      setActive(session); setAnswers({}); setGrade(null); setRevealed({}); setError(null);
      void homeQuery.refetch();
    },
    onError: error => setError(apiMessage(error, "Private Tutor could not prepare that study session.")),
  });

  const gradeMutation = useMutation({
    mutationFn: () => apiPost<{ grade: TutorGradeResult; session: TutorSession }>(`/api/v1/tutor/sessions/${active?.id}/grade`, { answers }),
    onSuccess: result => { setGrade(result.grade); setActive(result.session); setError(null); void homeQuery.refetch(); },
    onError: error => setError(apiMessage(error, "Private Tutor could not grade this quiz.")),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!moduleId) { setError("Choose a module before starting a tutor session."); return; }
    setError(null);
    createMutation.mutate();
  }

  function loadRecent(session: TutorSession) {
    setActive(session); setAnswers({}); setGrade(null); setRevealed({}); setError(null);
    setModuleId(String(session.module_id)); setLectureId(session.lecture_id ? String(session.lecture_id) : "");
    setMode(session.mode); setDifficulty(session.difficulty); setTopic(session.topic || ""); setRequestText(session.request_text || "");
  }

  const plannerPrompt = grade?.weak_areas.length
    ? `Schedule 45 minutes to revise ${grade.weak_areas.join(", ")} for ${active?.module_title || "my module"}.`
    : "";

  if (homeQuery.isPending) return <PageSkeleton label="Opening Private Tutor…" />;
  if (homeQuery.isError) return <section className="workspace-page"><div className="tutor-empty"><h1>Private Tutor unavailable</h1><p>{apiMessage(homeQuery.error, "V-SPACE could not load your study workspace.")}</p><button className="primary-button" onClick={() => void homeQuery.refetch()}>Retry</button></div></section>;

  const modules = homeQuery.data?.modules || [];
  const recent = homeQuery.data?.recent_sessions || [];
  const busy = createMutation.isPending || gradeMutation.isPending;

  return <section className="workspace-page private-tutor-page">
    <header className="workspace-page-header tutor-page-header">
      <div><span className="workspace-eyebrow"><Icon name="book"/> Learning intelligence</span><h1>Private Tutor</h1><p>Learn from your own V-SPACE material, test yourself, and turn weak areas into a smarter study plan.</p></div>
      <div className="tutor-trust"><Icon name="shield"/><div><strong>Grounded in your material</strong><span>Answers and questions stay tied to the module documents you select.</span></div></div>
    </header>

    <div className="tutor-layout">
      <aside className="tutor-setup-panel">
        <div className="tutor-panel-heading"><span>Study setup</span><strong>What are we learning?</strong></div>
        {!modules.length ? <div className="tutor-inline-empty"><Icon name="book"/><strong>No study modules yet</strong><p>Create a module and attach lecture material first.</p><a href="/modules" className="secondary-button">Open Modules</a></div> : <form onSubmit={submit} className="tutor-setup-form">
          <label><span>Module</span><select value={moduleId} onChange={event => { setModuleId(event.target.value); setLectureId(""); setActive(null); }} disabled={busy}><option value="">Choose a module</option>{modules.map(item => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label>
          <label><span>Lecture <em>optional</em></span><select value={lectureId} onChange={event => setLectureId(event.target.value)} disabled={!moduleId || busy}><option value="">Entire module</option>{lectures.map(item => <option value={item.id} key={item.id}>{item.lecture_number ? `${item.lecture_number}. ` : ""}{item.title}</option>)}</select></label>
          <label><span>Level</span><div className="tutor-segmented">{(["beginner","intermediate","advanced"] as TutorDifficulty[]).map(item => <button type="button" key={item} className={difficulty === item ? "active" : ""} onClick={() => setDifficulty(item)} disabled={busy}>{item}</button>)}</div></label>
          <label><span>Topic <em>optional</em></span><input value={topic} onChange={event => setTopic(event.target.value)} maxLength={500} placeholder="e.g. Fourier Transform" disabled={busy}/></label>
          <label><span>What do you want help with?</span><textarea value={requestText} onChange={event => setRequestText(event.target.value)} maxLength={1500} rows={4} placeholder="Explain the concept with examples, or tell V-SPACE what you're preparing for." disabled={busy}/></label>
          {mode === "quiz" ? <label><span>Questions</span><input type="range" min="3" max="10" value={questionCount} onChange={event => setQuestionCount(Number(event.target.value))}/><small>{questionCount} questions</small></label> : null}
          <button type="submit" className="primary-button tutor-start" disabled={busy || !moduleId}><Icon name="spark"/>{createMutation.isPending ? "Preparing your session…" : "Start learning"}</button>
        </form>}

        {recent.length ? <div className="tutor-recent"><div className="tutor-panel-heading compact"><span>Recent</span><strong>Study history</strong></div>{recent.slice(0,6).map(item => <button type="button" key={item.id} className={active?.id === item.id ? "active" : ""} onClick={() => loadRecent(item)}><span className={`tutor-mode-dot mode-${item.mode}`}/><span><strong>{item.content.title || item.module_title}</strong><small>{item.module_title} · {modeMeta.find(modeItem => modeItem.value === item.mode)?.label}{item.score.percentage !== null ? ` · ${item.score.percentage}%` : ""}</small></span><em>{formatTime(item.created_at)}</em></button>)}</div> : null}
      </aside>

      <main className="tutor-main">
        <div className="tutor-mode-bar" role="tablist" aria-label="Tutor mode">{modeMeta.map(item => <button type="button" role="tab" aria-selected={mode === item.value} className={mode === item.value ? "active" : ""} key={item.value} onClick={() => { setMode(item.value); setActive(null); setGrade(null); }} disabled={busy}><span>{item.label}</span><small>{item.description}</small></button>)}</div>

        {error ? <div className="tutor-alert"><strong>Couldn’t continue</strong><span>{error}</span></div> : null}

        {!active ? <div className="tutor-welcome-card"><div className="tutor-orb"><BrandMark/></div><span className="workspace-eyebrow">Private learning space</span><h2>{selectedModule ? `Ready for ${selectedModule.title}` : "Choose your material and start learning"}</h2><p>Private Tutor uses the same trusted Document Brain that powers V-SPACE. Pick a learning mode, select your module, and study from evidence you already own.</p><div className="tutor-capability-grid"><div><Icon name="documents"/><strong>Grounded</strong><span>Uses your linked module and lecture documents.</span></div><div><Icon name="spark"/><strong>Adaptive</strong><span>Choose beginner, intermediate, or advanced depth.</span></div><div><Icon name="check"/><strong>Measurable</strong><span>Quiz grading identifies exactly what to revise next.</span></div></div></div> : <article className="tutor-session-card">
          <header className="tutor-session-header"><div><span className="workspace-eyebrow">{modeMeta.find(item => item.value === active.mode)?.label} · {active.difficulty}</span><h2>{active.content.title}</h2><p>{active.module_title}{active.lecture_title ? ` · ${active.lecture_title}` : ""}{active.topic ? ` · ${active.topic}` : ""}</p></div><span className="tutor-grounded-badge"><Icon name="shield"/>{active.sources.length} source{active.sources.length === 1 ? "" : "s"}</span></header>

          {active.mode === "explain" || active.mode === "summarize" ? <div className="tutor-learning-content"><TutorMarkdown value={active.content.body_markdown || ""}/>{active.content.key_points?.length ? <section className="tutor-key-points"><h3>Key points</h3>{active.content.key_points.map((point,index) => <div key={index}><span>{index+1}</span><p>{point.text}</p><SourceChips ids={point.source_ids} sources={active.sources}/></div>)}</section> : null}{active.content.check_questions?.length ? <section className="tutor-self-check"><h3>Quick self-check</h3>{active.content.check_questions.map((question,index) => <div key={index}><span>Q{index+1}</span><p>{question}</p></div>)}</section> : null}</div> : null}

          {active.mode === "quiz" ? <div className="tutor-quiz"><p className="tutor-session-intro">{active.content.instructions}</p>{active.content.questions?.map((question,index) => {
            const result = grade?.results.find(item => item.id === question.id);
            return <fieldset className={`tutor-question ${result ? result.correct ? "correct" : "incorrect" : ""}`} key={question.id}><legend><span>Question {index+1}</span>{question.topic ? <em>{question.topic}</em> : null}</legend><h3>{question.prompt}</h3><div className="tutor-options">{question.options?.map((option,optionIndex) => <label key={optionIndex} className={result && optionIndex === result.correct_index ? "correct-option" : result && optionIndex === result.selected_index && !result.correct ? "wrong-option" : ""}><input type="radio" name={`question-${question.id}`} disabled={Boolean(grade)} checked={answers[question.id] === optionIndex} onChange={() => setAnswers(current => ({...current,[question.id]:optionIndex}))}/><span>{String.fromCharCode(65+optionIndex)}</span><p>{option}</p></label>)}</div>{result ? <div className="tutor-answer-review"><strong>{result.correct ? "Correct" : `Correct answer: ${result.correct_answer}`}</strong><p>{result.explanation}</p><SourceChips ids={result.source_ids} sources={active.sources}/></div> : null}</fieldset>;
          })}{!grade ? <button type="button" className="primary-button tutor-grade-button" disabled={busy || Object.keys(answers).length === 0} onClick={() => gradeMutation.mutate()}>{gradeMutation.isPending ? "Checking answers…" : "Check my answers"}</button> : <div className="tutor-grade-summary"><ScoreRing percentage={grade.percentage}/><div><span className="workspace-eyebrow">Your result</span><h3>{grade.correct} of {grade.total} correct</h3><p>{grade.percentage >= 80 ? "Strong work. You understand most of this material." : grade.percentage >= 60 ? "Good foundation. A short targeted review will help." : "This topic needs another pass. Focus on the weak areas below."}</p>{grade.weak_areas.length ? <div className="tutor-weak-areas"><strong>Review next</strong>{grade.weak_areas.map(item => <span key={item}>{item}</span>)}</div> : null}{plannerPrompt ? <a className="secondary-button tutor-plan-revision" href={`/planner?prompt=${encodeURIComponent(plannerPrompt)}`}><Icon name="calendar"/> Plan revision</a> : null}</div></div>}</div> : null}

          {active.mode === "practice" ? <div className="tutor-practice">{active.content.questions?.map((question,index) => <article key={question.id} className="tutor-practice-card"><span>Practice {index+1}</span><h3>{question.prompt}</h3><SourceChips ids={question.source_ids} sources={active.sources}/><div className="tutor-reveal-actions"><button type="button" onClick={() => setRevealed(current => ({...current,[question.id]:"hint"}))}>Show hint</button><button type="button" onClick={() => setRevealed(current => ({...current,[question.id]:"solution"}))}>Show solution</button></div>{revealed[question.id] === "hint" ? <div className="tutor-reveal"><strong>Hint</strong><p>{question.hint || "Start from the definitions in your selected material."}</p></div> : null}{revealed[question.id] === "solution" ? <div className="tutor-reveal solution"><strong>Worked solution</strong><p>{question.solution}</p></div> : null}</article>)}</div> : null}

          {active.mode === "flashcards" ? <div className="tutor-flashcards">{active.content.cards?.map((card,index) => { const flipped = revealed[card.id] === "back"; return <button type="button" className={`tutor-flashcard ${flipped ? "flipped" : ""}`} key={card.id} onClick={() => setRevealed(current => ({...current,[card.id]:flipped ? "hint" : "back"}))}><span>Card {index+1}</span><strong>{flipped ? card.back : card.front}</strong><small>{flipped ? "Tap to see question" : "Tap to reveal"}</small><SourceChips ids={card.source_ids} sources={active.sources}/></button>; })}</div> : null}

          {active.mode !== "quiz" && active.content.source_ids ? <SourceChips ids={active.content.source_ids} sources={active.sources}/> : null}

          {active.sources.length ? <details className="tutor-sources"><summary><span><Icon name="documents"/><strong>Study sources</strong></span><small>{active.sources.length} grounded reference{active.sources.length === 1 ? "" : "s"}</small></summary><div>{active.sources.map(source => <article key={source.source_id}><span>S{source.source_id}</span><div><strong>{source.filename}</strong><small>{[source.page ? `Page ${source.page}` : null, source.section].filter(Boolean).join(" · ") || "Module material"}</small>{source.evidence ? <p>{source.evidence}</p> : null}</div></article>)}</div></details> : null}
        </article>}
      </main>
    </div>
  </section>;
}
