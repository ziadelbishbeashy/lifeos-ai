export type User = {
  id: number;
  name: string;
  email: string;
};

export type SessionState = {
  authenticated: boolean;
  user: User | null;
};

export type DashboardTask = {
  id: number;
  title: string;
  description: string | null;
  status: string;
  importance: string | null;
  module: string | null;
  deadline: string | null;
  priority_score: number | null;
  project: { id: number; title: string } | null;
};

export type DashboardProject = {
  id: number;
  title: string;
  status: string;
  priority: string;
  progress: number;
  current_phase: string | null;
  project_type: string | null;
  deadline: string | null;
};

export type DashboardData = {
  today: string;
  counts: {
    projects: number;
    active_projects: number;
    tasks: number;
    general_tasks: number;
    project_tasks: number;
    open_tasks: number;
    completed_tasks: number;
    blocked_tasks: number;
    overdue_tasks: number;
    notes: number;
    documents: number;
  };
  completion_rate: number;
  average_project_progress: number;
  focus_task: DashboardTask | null;
  upcoming_tasks: DashboardTask[];
  latest_projects: DashboardProject[];
};

export type Project = {
  id: number;
  title: string;
  project_type: string | null;
  description: string | null;
  goal: string | null;
  tech_stack: string | null;
  project_folder: string | null;
  github_link: string | null;
  demo_link: string | null;
  start_date: string | null;
  deadline: string | null;
  status: string;
  priority: string;
  current_phase: string | null;
  progress: number;
  created_at: string | null;
  updated_at: string | null;
};

export type ProjectSummary = Pick<
  Project,
  "id" | "title" | "status" | "priority" | "progress" | "deadline"
>;

export type Task = {
  id: number;
  project_id: number | null;
  project: { id: number; title: string } | null;
  title: string;
  description: string | null;
  module: string | null;
  tags: string | null;
  importance: string;
  difficulty: string;
  deadline: string | null;
  status: string;
  priority_score: number | null;
  reason: string | null;
  reminder_enabled: boolean;
  reminder_type: string;
  reminder_datetime: string | null;
  is_recurring: boolean;
  recurrence_type: string;
  recurrence_interval: number;
  recurrence_end_date: string | null;
  next_occurrence_date: string | null;
  created_at: string | null;
  completed_at: string | null;
};

export type ProjectCard = Project & {
  task_progress: number;
  total_tasks: number;
  completed_tasks: number;
  open_tasks: number;
  overdue_tasks: number;
  note_count: number;
  health: { label?: string; tone?: string; message?: string } | null;
  next_task: Task | null;
};

export type ProjectListData = {
  items: ProjectCard[];
  counts: {
    total: number;
    active: number;
    attention: number;
    completed: number;
  };
};

export type TaskListData = {
  items: Task[];
  projects: ProjectSummary[];
  module_names: string[];
  counts: {
    total: number;
    completed: number;
    pending: number;
    in_progress: number;
    blocked: number;
    general: number;
    project: number;
    recurring: number;
    overdue: number;
    due_soon: number;
  };
};

export type NoteSummary = {
  id: number;
  project_id: number | null;
  title: string;
  content: string;
  note_type: string;
  is_pinned: boolean;
  updated_at: string | null;
};

export type DocumentSummary = {
  id: number;
  project_id: number | null;
  filename: string;
  version_label: string;
  version_number: number | null;
  is_current_version: boolean;
  uploaded_at: string | null;
  has_text: boolean;
  summary: string | null;
};

export type ProjectWorkspaceData = {
  project: Project;
  tasks: Task[];
  recent_notes: NoteSummary[];
  documents: DocumentSummary[];
  metrics: {
    total_tasks: number;
    completed_tasks: number;
    pending_tasks: number;
    in_progress_tasks: number;
    blocked_tasks: number;
    overdue_tasks: number;
    due_soon_tasks: number;
    task_progress: number;
    notes_count: number;
    document_count: number;
    searchable_document_count: number;
  };
  project_health: { label?: string; tone?: string; message?: string } | null;
  days_to_deadline: number | null;
  next_task: Task | null;
};

export type ProjectInput = {
  title: string;
  project_type?: string;
  description?: string;
  goal?: string;
  tech_stack?: string;
  project_folder?: string;
  github_link?: string;
  demo_link?: string;
  start_date?: string;
  deadline?: string;
  no_deadline?: boolean;
  status?: string;
  priority?: string;
  current_phase?: string;
  progress?: number;
};

export type TaskInput = {
  project_id?: number | null;
  forced_project_id?: number;
  title: string;
  description?: string;
  module?: string;
  tags?: string;
  importance?: string;
  difficulty?: string;
  deadline?: string;
  status?: string;
  reminder_enabled?: boolean;
  reminder_type?: string;
  reminder_date?: string;
  reminder_time?: string;
  is_recurring?: boolean;
  recurrence_type?: string;
  recurrence_interval?: number;
  recurrence_end_date?: string;
};
