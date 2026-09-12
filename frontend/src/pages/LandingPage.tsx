import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useSession } from "../auth/session";
import { navigate } from "../core/navigation";
import { BrandMark, Icon, type IconName } from "../components/VSpaceUi";

const views = ["My day", "Knowledge", "Ask V-SPACE"] as const;
type PreviewView = typeof views[number];
const questions = [
  { question: "What can I use V-SPACE AI for?", answer: "Keep projects, tasks, notes and documents together. Plan your workload, focus on your next action, ask questions about connected material, and use study modes to explore a topic." },
  { question: "How is it different from a task manager?", answer: "Your task list is connected to the work behind it: project goals, notes, documents and deadlines. The assistant can use that context to help you understand a problem and decide what to do next." },
  { question: "Does AI make changes without asking me?", answer: "Important AI-proposed workspace changes go through a review and confirmation step. For example, a planner preview does not save a schedule. You review the proposal and explicitly accept it." },
  { question: "Can I ask questions about my documents?", answer: "Yes. Document Brain supports PDFs, text extraction, search, analysis and questions grounded in the document. When source evidence is available, you can open it and verify the answer against the original material." },
  { question: "Is it just for studying?", answer: "V-SPACE supports study, personal projects and professional work. Use the tools that fit your day, whether you’re preparing for an exam, building a product or organizing your next project." },
];

export function LandingPage() {
  const session = useSession();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuTrigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previousClass = document.body.className;
    const previousTheme = document.documentElement.getAttribute("data-theme");
    const previousTitle = document.title;
    document.body.className = "vsl-body";
    document.documentElement.setAttribute("data-theme", "dark");
    document.title = "V-SPACE AI — Your intelligent space for everything";
    return () => {
      document.body.className = previousClass;
      if (previousTheme) document.documentElement.setAttribute("data-theme", previousTheme);
      else document.documentElement.removeAttribute("data-theme");
      document.title = previousTitle;
    };
  }, []);
  useEffect(() => { if (session.data?.authenticated) navigate("/dashboard", true); }, [session.data?.authenticated]);
  useEffect(() => {
    if (!menuOpen) return;
    const escape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") { setMenuOpen(false); menuTrigger.current?.focus(); }
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [menuOpen]);

  if (session.data?.authenticated) return null;
  return <div className="vsl-landing">
    <a className="vsl-skip" href="#vsl-main">Skip to content</a>
    <header className="vsl-header">
      <div className="vsl-header-inner">
        <a href="/" className="vsl-brand" aria-label="V-SPACE AI home"><BrandMark/><span>V-SPACE <b>AI</b></span></a>
        <nav className={`vsl-nav ${menuOpen ? "is-open" : ""}`} id="vsl-navigation" aria-label="Website navigation" onClick={() => setMenuOpen(false)}>
          <a href="#features">The workspace</a><a href="#workflow">How it works</a><a href="#faq">FAQs</a>
          <a className="vsl-mobile-login" href="/login">Log in</a>
        </nav>
        <div className="vsl-header-actions"><a className="vsl-login" href="/login">Log in</a><a className="vsl-button vsl-button-small" href="/register">Get started<Icon name="arrow"/></a><button ref={menuTrigger} type="button" className="vsl-menu" aria-label={menuOpen ? "Close navigation" : "Open navigation"} aria-controls="vsl-navigation" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}><Icon name={menuOpen ? "close" : "menu"}/></button></div>
      </div>
    </header>
    <main id="vsl-main" tabIndex={-1}>
      <section className="vsl-hero">
        <div className="vsl-hero-halo" aria-hidden="true"/>
        <div className="vsl-container vsl-hero-copy">
          <a className="vsl-announcement" href="#workspace-preview"><span className="vsl-status-dot"/>Your work. Connected.<span className="vsl-announcement-divider"/><span>Meet V-SPACE AI</span><Icon name="arrow"/></a>
          <h1>Make space for<br/><span>what matters.</span></h1>
          <p>One intelligent workspace for your projects, knowledge, and next steps.<br className="vsl-desktop-break"/> Turn everything on your mind into something you move forward.</p>
          <div className="vsl-hero-actions"><a href="/register" className="vsl-button">Create your workspace<Icon name="arrow"/></a><a href="#workspace-preview" className="vsl-button vsl-button-secondary"><Icon name="grid"/>Explore the workspace</a></div>
          <div className="vsl-hero-note"><Icon name="shield"/>AI helps you think. You stay in control.</div>
        </div>
        <div className="vsl-container vsl-preview-wrap" id="workspace-preview"><WorkspacePreview/></div>
      </section>
      <div className="vsl-container vsl-capabilities" aria-label="Connected workspace tools">{([ ["projects", "Projects & tasks"], ["documents", "Document Brain"], ["spark", "Ask V-SPACE"], ["calendar", "Smart Planner"], ["book", "Private Tutor"], ["focus", "Focus Studio"] ] as [IconName, string][]).map(([icon, label]) => <span key={label}><Icon name={icon}/>{label}</span>)}</div>

      <section className="vsl-container vsl-section" id="features">
        <div className="vsl-section-heading"><div><span className="vsl-eyebrow">A home for your whole process</span><h2>Less switching.<br/>More moving forward.</h2></div><p>The plan, the source material, the next action.<br/>Bring them together, so you can get back to doing.</p></div>
        <div className="vsl-feature-grid">
          <article className="vsl-feature vsl-feature-wide"><FeatureHeading icon="projects" label="Build with direction" title="Big ideas. Clear next steps." text="Give every project a goal, every task a place, and your attention a direction."/><div className="vsl-project-demo" aria-label="Example project overview"><div className="vsl-project-demo-top"><span className="vsl-project-symbol"><Icon name="projects"/></span><div><strong>Launch something meaningful</strong><small>Personal project · In progress</small></div><span className="vsl-tag">On track</span></div><div className="vsl-demo-progress"><span/></div><div className="vsl-project-demo-bottom"><span>Outline the idea</span><span>Build the first version</span><span>Share it</span></div></div></article>
          <article className="vsl-feature vsl-feature-wide"><FeatureHeading icon="documents" label="Make knowledge useful" title="Find the answer. Keep the source." text="Search your PDFs and ask grounded questions. Follow the evidence back to the material."/><div className="vsl-source-demo"><div><Icon name="documents"/><span>Research notes.pdf</span><small>Example source</small></div><blockquote>“Start with the problem you want to solve. Let the evidence guide the next step.”</blockquote><span className="vsl-source-reference"><Icon name="book"/>Page 12 · Product discovery</span></div></article>
          <article className="vsl-feature"><FeatureHeading icon="book" label="Learn at your pace" title="Make it click." text="Explain a concept, summarize study material, or turn a topic into practice questions."/><StudyCard/></article>
          <article className="vsl-feature"><FeatureHeading icon="focus" label="Protect your attention" title="One thing at a time." text="Choose a task, start a focus session, and park distracting thoughts for later."/><div className="vsl-focus-demo" aria-label="Illustration of a 25 minute focus session"><div className="vsl-focus-orbit"><Icon name="focus"/><strong>25:00</strong><span>Time to make progress</span></div><span className="vsl-focus-task"><span className="vsl-status-dot"/>Finish the first draft</span></div></article>
          <article className="vsl-feature vsl-feature-ai"><FeatureHeading icon="spark" label="Think with context" title="Ask a better-connected assistant." text="Explore an idea, understand your priorities, or work through a question with your project context close by."/><div className="vsl-ai-prompts"><span>What should I focus on today?</span><span>Explain this from my study notes.</span><span>Help me plan my next step.</span></div><a href="/register" className="vsl-text-link">Meet your workspace<Icon name="arrow"/></a></article>
        </div>
      </section>

      <section className="vsl-workflow" id="workflow"><div className="vsl-container">
        <div className="vsl-section-heading vsl-heading-centered"><span className="vsl-eyebrow">A little clarity goes a long way</span><h2>From “where do I start?”<br/>to “I’ve got this.”</h2></div>
        <div className="vsl-steps">{[
          { icon: "plus" as const, title: "Bring it all in", text: "Capture the project, the notes, the PDF, the task. Give your work a home." },
          { icon: "spark" as const, title: "Connect the dots", text: "Ask questions, explore your material, and build a plan around what matters." },
          { icon: "check" as const, title: "Make your next move", text: "Review the suggestion, choose your next step, and get into a focused session." },
        ].map((step, i) => <article key={step.title}><div className="vsl-step-top"><span className="vsl-step-icon"><Icon name={step.icon}/></span><span>0{i + 1}</span></div><h3>{step.title}</h3><p>{step.text}</p></article>)}</div>
      </div></section>

      <section className="vsl-container vsl-section vsl-trust"><div className="vsl-trust-copy"><span className="vsl-eyebrow">Your workspace. Your decisions.</span><h2>Helpful intelligence.<br/><span>Human control.</span></h2><p>AI should help you understand your work and move it forward. Important changes stay yours to review and confirm.</p><ul><li><Icon name="check"/>Check the evidence behind grounded answers</li><li><Icon name="check"/>Preview plans before saving your schedule</li><li><Icon name="check"/>Review important AI-proposed changes</li></ul></div><div className="vsl-review-demo"><div className="vsl-review-top"><span className="vsl-step-icon"><Icon name="shield"/></span><span>Designed around your decisions<small>Illustrated confirmation flow</small></span></div><div className="vsl-review-row"><span>01</span><div><strong>AI suggests a plan</strong><small>A proposal, ready for you to review.</small></div><Icon name="spark"/></div><div className="vsl-review-row"><span>02</span><div><strong>You check the details</strong><small>The timing, the workload, the next steps.</small></div><Icon name="search"/></div><div className="vsl-review-row vsl-review-final"><span>03</span><div><strong>You choose to confirm</strong><small>Only then is the proposed schedule saved.</small></div><Icon name="check"/></div></div></section>

      <section className="vsl-container vsl-section vsl-faq" id="faq"><div><span className="vsl-eyebrow">A few things you might wonder</span><h2>Good questions.<br/>Clear answers.</h2><p>Get to know your next workspace.</p></div><div className="vsl-faq-list">{questions.map(item => <details key={item.question}><summary>{item.question}<span aria-hidden="true">+</span></summary><p>{item.answer}</p></details>)}</div></section>
      <section className="vsl-container vsl-final-cta"><div className="vsl-cta-mark"><BrandMark/></div><span className="vsl-eyebrow">Virtual Smart Space</span><h2>Your next chapter<br/>starts with a little space.</h2><p>Think. Organize. Create. Go further.</p><a href="/register" className="vsl-button">Create your workspace<Icon name="arrow"/></a></section>
    </main>
    <footer className="vsl-container vsl-footer"><div><a href="/" className="vsl-brand"><BrandMark/><span>V-SPACE <b>AI</b></span></a><p>Your intelligent space for everything.</p></div><nav aria-label="Footer navigation"><a href="#features">The workspace</a><a href="#faq">FAQs</a><a href="/login">Log in</a></nav><small>© {new Date().getFullYear()} V-SPACE AI</small></footer>
  </div>;
}

function FeatureHeading({ icon, label, title, text }: { icon: IconName; label: string; title: string; text: string }) {
  return <><span className="vsl-feature-label"><Icon name={icon}/>{label}</span><h3>{title}</h3><p>{text}</p></>;
}
function StudyCard() {
  const [revealed, setRevealed] = useState(false);
  return <button type="button" className="vsl-study-card" aria-expanded={revealed} onClick={() => setRevealed(!revealed)}><span>Try a sample flashcard<Icon name="book"/></span><strong>{revealed ? "Recall an idea from memory before checking your notes." : "What is active recall?"}</strong><small>{revealed ? "Click to see the question" : "Click to reveal the answer"}<Icon name="arrow"/></small></button>;
}
function WorkspacePreview() {
  const [view, setView] = useState<PreviewView>("My day");
  const [complete, setComplete] = useState(false);
  const [answer, setAnswer] = useState(false);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  function onTabKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? 2 : (index + (event.key === "ArrowRight" ? 1 : -1) + 3) % 3;
    setView(views[next]); tabRefs.current[next]?.focus();
  }
  return <>
    <div className="vsl-preview-tabs" role="tablist" aria-label="Explore the sample workspace">{views.map((item, i) => <button type="button" role="tab" key={item} id={`vsl-tab-${i}`} aria-selected={view === item} aria-controls="vsl-preview-panel" tabIndex={view === item ? 0 : -1} ref={node => { tabRefs.current[i] = node; }} onKeyDown={event => onTabKey(event, i)} onClick={() => setView(item)}><Icon name={i === 0 ? "dashboard" : i === 1 ? "documents" : "spark"}/>{item}</button>)}</div>
    <div className="vsl-product-window">
      <div className="vsl-window-top"><span className="vsl-window-dots" aria-hidden="true"><i/><i/><i/></span><span><Icon name="shield"/>Your personal workspace</span><span className="vsl-sample-label">Interactive preview</span></div>
      <div className="vsl-window-body"><aside className="vsl-preview-sidebar" aria-hidden="true"><div className="vsl-preview-brand"><BrandMark/><strong>V-SPACE <b>AI</b></strong></div><small>WORKSPACE</small>{([ ["dashboard", "My day"], ["projects", "Projects"], ["tasks", "Tasks"], ["calendar", "Smart Planner"], ["spark", "Ask V-SPACE"], ["documents", "Knowledge"] ] as [IconName,string][]).map(([icon,label]) => <div key={label} className={view === label ? "active" : ""}><Icon name={icon}/>{label}</div>)}<div className="vsl-preview-person"><span>Y</span><strong>Your space<small>A little progress, every day</small></strong></div></aside>
        <div className="vsl-preview-canvas" role="tabpanel" id="vsl-preview-panel" aria-labelledby={`vsl-tab-${views.indexOf(view)}`}>
          <div className="vsl-demo-heading"><div><span className="vsl-eyebrow">{view === "My day" ? "YOUR SPACE, YOUR PACE" : view === "Knowledge" ? "GOOD IDEAS, WITH CONTEXT" : "YOUR CONNECTED INTELLIGENCE"}</span><h2>{view === "My day" ? "A little clarity for your day." : view === "Knowledge" ? "Everything you’re learning, connected." : "Think it through, together."}</h2></div><span className="vsl-demo-avatar">Y</span></div>
          {view === "My day" ? <><button type="button" className="vsl-demo-ask" onClick={() => { setView("Ask V-SPACE"); setAnswer(true); }}><Icon name="spark"/><span>What should I focus on today?</span><span className="vsl-demo-send"><Icon name="arrow"/></span></button><div className="vsl-demo-columns"><div className="vsl-demo-panel"><div className="vsl-demo-panel-heading"><strong>Your next steps</strong><span>Today</span></div><button type="button" className={`vsl-demo-task ${complete ? "is-complete" : ""}`} aria-pressed={complete} onClick={() => setComplete(!complete)}><span className="vsl-demo-check">{complete ? <Icon name="check"/> : null}</span><span><strong>Bring the first idea to life</strong><small>Personal project <b>High priority</b></small></span></button><div className="vsl-demo-task vsl-demo-static"><span className="vsl-demo-check"/><span><strong>Review your research notes</strong><small>Learning <b className="vsl-tag-teal">Ready to explore</b></small></span></div><div className="vsl-demo-progress-caption"><span>A little progress adds up.</span><strong>{complete ? "1 of 2 complete" : "Ready when you are"}</strong></div><div className="vsl-demo-progress"><span style={{ width: complete ? "50%" : "8%" }}/></div></div><div className="vsl-demo-panel vsl-demo-timeline"><div className="vsl-demo-panel-heading"><strong>Room for what matters</strong><Icon name="calendar"/></div><div><time>09:00</time><span><strong>Deep work</strong><small>Bring the first idea to life</small></span></div><div><time>10:00</time><span><strong>Time to recharge</strong><small>A little breathing room</small></span></div><div><time>10:15</time><span><strong>Learn something new</strong><small>Research & reading</small></span></div></div></div><div className="vsl-demo-bottom"><Icon name="shield"/><span>Your plan. Your pace. Your decision.</span><span>Sample day</span></div></> : view === "Knowledge" ? <div className="vsl-demo-knowledge"><div className="vsl-demo-panel"><div className="vsl-demo-panel-heading"><strong>Your knowledge</strong><Icon name="documents"/></div>{["Research notes.pdf", "Ideas for the next chapter", "Project brief.pdf"].map((name,i) => <div className="vsl-demo-file" key={name}><span><Icon name={i === 1 ? "notes" : "documents"}/></span><div><strong>{name}</strong><small>{i === 1 ? "Note · Personal project" : "PDF · Connected material"}</small></div><Icon name="chevron"/></div>)}</div><div className="vsl-demo-panel vsl-demo-source"><span className="vsl-feature-label"><Icon name="spark"/>From a question to a source</span><h3>What’s the starting point?</h3><p>Define the problem before planning the solution. Your research notes make that the first step.</p><span className="vsl-source-reference"><Icon name="documents"/>Research notes.pdf · p. 12</span><small>Illustrated answer and source</small></div></div> : <div className="vsl-demo-conversation"><div className="vsl-demo-user">What should I focus on today?</div><div className="vsl-demo-response"><span className="vsl-demo-ai-mark"><BrandMark/></span><div><strong>Let’s make the next step clear.</strong>{answer ? <><p>Start with <b>Bring the first idea to life</b>. It’s the high-priority task in your sample project.</p><div className="vsl-demo-answer-plan"><Icon name="focus"/><span>One focused hour<strong>Make a first draft, then review it.</strong></span></div><small>Example response · no live AI request</small></> : <><p>Explore how your assistant can connect a question to the work behind it.</p><button type="button" className="vsl-text-link" onClick={() => setAnswer(true)}>Show example answer<Icon name="arrow"/></button></>}</div></div></div>}
        </div>
      </div>
    </div>
    <p className="vsl-preview-caption"><span className="vsl-status-dot"/>Explore the tabs. Try completing a task. This is a sample workspace.</p>
  </>;
}
