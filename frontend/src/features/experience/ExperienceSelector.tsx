import type { ExperienceDefinition, ExperienceKey } from "../../api/types";


export const FALLBACK_EXPERIENCE_OPTIONS: ExperienceDefinition[] = [
  { key: "student", label: "Student", short_label: "Study", description: "Classes, modules, deadlines, study planning and tutoring.", workspace_label: "Student workspace", module_label: "Modules", modules_visible: true, home_focus: "study_and_execution", ask_prompts: [] },
  { key: "self_learning", label: "Self-Learning", short_label: "Learning", description: "Build skills, learn independently, practice and track progress.", workspace_label: "Learning workspace", module_label: "Learning", modules_visible: true, home_focus: "learning_and_execution", ask_prompts: [] },
  { key: "professional", label: "Professional", short_label: "Work", description: "Projects, deadlines, documents, focus and work intelligence.", workspace_label: "Work workspace", module_label: "Modules", modules_visible: false, home_focus: "projects_and_execution", ask_prompts: [] },
  { key: "personal", label: "Personal", short_label: "Personal", description: "Tasks, personal projects, notes, documents and daily organization.", workspace_label: "Personal workspace", module_label: "Modules", modules_visible: false, home_focus: "personal_execution", ask_prompts: [] },
];

const experienceSymbols: Record<string, string> = {
  student: "🎓",
  self_learning: "📚",
  professional: "💼",
  personal: "🏠",
};

export function ExperienceSelector({
  options,
  selected,
  onChange,
  compact = false,
}: {
  options: ExperienceDefinition[];
  selected: ExperienceKey | null;
  onChange: (key: ExperienceKey) => void;
  compact?: boolean;
}) {
  return <div className={`experience-choice-grid ${compact ? "compact" : ""}`}>
    {options.map((option) => {
      const active = selected === option.key;
      return <button
        type="button"
        key={option.key}
        className={`experience-choice-card ${active ? "active" : ""}`}
        onClick={() => onChange(option.key)}
        aria-pressed={active}
      >
        <span className="experience-choice-icon" aria-hidden="true">{experienceSymbols[option.key] || "L"}</span>
        <span className="experience-choice-copy">
          <strong>{option.label}</strong>
          <small>{option.description}</small>
        </span>
        <span className="experience-choice-check" aria-hidden="true">{active ? "✓" : ""}</span>
      </button>;
    })}
  </div>;
}
