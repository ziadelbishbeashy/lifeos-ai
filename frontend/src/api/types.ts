export type ProactiveNotification = {
  id: number;
  event_id: number;
  event_type: string | null;
  category: string;
  severity: string;
  status: "unread" | "read" | "dismissed" | "resolved" | string;
  title: string;
  message: string;
  action: { label: string | null; href: string | null; ask_query: string | null };
  resource: { type: string | null; id: number | null; project_id: number | null };
  created_at: string | null;
  read_at: string | null;
  dismissed_at: string | null;
  verified_from_state: boolean;
};

export type ProactiveNotificationData = {
  items: ProactiveNotification[];
  counts: { unread: number; returned: number; created: number; resolved: number };
  verified_from_state: boolean;
  workspace_mutation: boolean;
  delivery: "in_app" | string;
};

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

export type IntelligenceActionOption = {
  type: "create_task" | "create_note" | "refresh_document_analysis" | string;
  label: string;
  risk_level: string;
};

export type IntelligenceActionProposal = {
  id: number;
  action_type: string;
  status: "pending" | "executing" | "confirmed" | "dismissed" | "failed" | string;
  title: string;
  reason?: string | null;
  target: { type: string; id: number | null };
  project_id?: number | null;
  payload: Record<string, unknown>;
  evidence?: TodayPriority["evidence"];
  risk_level: string;
  requires_confirmation: boolean;
  execution?: { resource_type: string; resource_id: number } | null;
  failure_message?: string | null;
};

export type TodayPriority = {
  project_id: number;
  project_title: string;
  category: string;
  severity: string;
  title: string;
  reason: string;
  recommended_action: string;
  actions: IntelligenceActionOption[];
  evidence: Array<{
    source_type: string;
    source_id: number | null;
    label: string;
    field: string;
    freshness: string;
  }>;
};

export type TodayIntelligenceData = {
  today: string;
  attention_level: string;
  summary: string;
  priorities: TodayPriority[];
  counts: {
    total_owned_projects: number;
    reviewed_projects: number;
    ranked_priorities: number;
    high: number;
    medium: number;
    low: number;
  };
  context_limited: boolean;
  verified_from_state: boolean;
  read_only: boolean;
};


export type HomeInsightItem = {
  type: string;
  title: string;
  detail: string;
  severity: string;
  status?: string | null;
  deadline?: string | null;
  project_id?: number | null;
  project_title?: string | null;
  module_id?: number | null;
  module_title?: string | null;
  object_id?: number | null;
  source?: { type: string; id: number | null } | null;
  action_hint?: string | null;
};

export type HomeInsightSection = {
  kind: string;
  summary: string;
  items: HomeInsightItem[];
  counts: Record<string, number>;
  context_limited: boolean;
  verified_from_state: boolean;
  read_only: boolean;
};

export type HomeActivityItem = {
  event_type: string;
  object_type: string;
  object_id?: number | null;
  project_id?: number | null;
  project_title?: string | null;
  title: string;
  summary?: string | null;
  occurred_at: string;
  source: string;
  changes?: Record<string, unknown>;
};

export type HomeActivitySection = {
  window: { start_at: string; end_at: string; label: string };
  scope: { type: string; id: number | null; label: string };
  summary: string;
  items: HomeActivityItem[];
  counts: Record<string, number>;
  total_items: number;
  context_limited: boolean;
  verified_from_state: boolean;
  read_only: boolean;
};

export type HomeIntelligenceData = {
  today: string;
  briefing: {
    headline: string;
    summary: string;
    attention_level: string;
    signals: Array<{ key: string; label: string; count: number; tone: string }>;
  };
  focus: TodayIntelligenceData;
  deadlines: HomeInsightSection;
  documents: HomeInsightSection;
  study: HomeInsightSection;
  activity: HomeActivitySection;
  context_limited: boolean;
  verified_from_state: boolean;
  read_only: boolean;
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


export type ProjectQuestion = {
  id: number;
  project_id: number;
  question: string;
  answer: string | null;
  sources: Array<Record<string, unknown>>;
  status: string;
  error_message: string | null;
  created_at: string | null;
};


export type DocumentSuggestion = {
  id: number;
  document_id: number;
  title: string;
  description: string | null;
  priority: string;
  deadline: string | null;
  source: Record<string, unknown> | null;
  status: string;
  lifecycle_label: string;
  matched_task_id: number | null;
  created_task_id: number | null;
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
  project_question_history: ProjectQuestion[];
  document_suggestions: DocumentSuggestion[];
  pending_document_suggestion_count: number;
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

export type Lecture = {
  id: number;
  module_id: number;
  title: string;
  lecture_number: number | null;
  lecture_date: string | null;
  status: string;
  topics: string | null;
  summary: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type ModuleQuestion = {
  id: number;
  module_id: number;
  lecture_id: number | null;
  question: string;
  answer: string | null;
  sources: Array<{
    source_id?: number;
    document_id?: number;
    filename?: string;
    page?: number | string | null;
    section?: string | null;
    evidence?: string | null;
    content_type?: string;
    table_id?: number | null;
  }>;
  status: string;
  error_message: string | null;
  created_at: string | null;
};

export type DocumentCollectionSummary = {
  id: number;
  name: string;
  description: string | null;
  document_count: number;
  created_at: string | null;
  updated_at: string | null;
};

export type LearningModule = {
  id: number;
  title: string;
  description: string | null;
  subject: string | null;
  status: string;
  created_at: string | null;
  updated_at: string | null;
  counts: {
    lectures: number;
    documents: number;
    notes: number;
    tasks: number;
    collections: number;
  };
};

export type ModuleDocument = DocumentSummary & { lecture_id: number | null };
export type ModuleNote = NoteSummary & { lecture_id: number | null };
export type ModuleTask = Task & { lecture_id: number | null };

export type LearningModuleDetail = LearningModule & {
  lectures: Lecture[];
  documents: ModuleDocument[];
  notes: ModuleNote[];
  tasks: ModuleTask[];
  collections: DocumentCollectionSummary[];
};

export type ModuleDetailData = {
  item: LearningModuleDetail;
  question_history: ModuleQuestion[];
  lecture_question_history: Record<string, ModuleQuestion[]>;
  available: {
    documents: DocumentSummary[];
    notes: NoteSummary[];
    tasks: Task[];
    collections: DocumentCollectionSummary[];
  };
  max_upload_bytes: number;
};

export type AutomationTriggerType = "schedule_daily" | "schedule_weekly" | "event" | string;
export type AutomationActionType = "today_briefing" | "portfolio_review" | "project_review" | "risk_escalation" | "unhandled_followup" | "attention_notice" | string;

export type AutomationVisualNodeId = "trigger" | "intelligence" | "delivery";

export type AutomationVisualGraph = {
  version: number;
  nodes: Array<{
    id: AutomationVisualNodeId;
    kind: AutomationVisualNodeId;
    position: { x: number; y: number };
    semantic_type?: string;
  }>;
  edges: Array<{ id: string; source: AutomationVisualNodeId; target: AutomationVisualNodeId }>;
  safety?: { workspace_mutation: boolean; delivery: string; future_workspace_actions_require: string };
};

export type LifeOSAutomation = {
  id: number;
  name: string;
  description: string | null;
  enabled: boolean;
  status: string;
  trigger: { type: AutomationTriggerType; config: Record<string, unknown> };
  action: { type: AutomationActionType; config: Record<string, unknown> };
  visual_graph: AutomationVisualGraph;
  timezone: string;
  next_run_at: string | null;
  last_run_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  safety: { workspace_mutation: boolean; confirmation_boundary: string };
};

export type AutomationTemplate = {
  key: string;
  name: string;
  description: string;
  trigger_type: AutomationTriggerType;
  trigger_config: Record<string, unknown>;
  action_type: AutomationActionType;
  action_config: Record<string, unknown>;
};

export type AutomationRegistryData = {
  triggers: Array<{ type: AutomationTriggerType; label: string; description: string; fields: string[] }>;
  event_types: string[];
  actions: Array<{ type: AutomationActionType; label: string; description: string; scope: string }>;
  templates: AutomationTemplate[];
  limits: { max_automations_per_user: number };
  visual_flow: {
    version: number;
    node_order: AutomationVisualNodeId[];
    delivery_type: string;
    connections_fixed: boolean;
    layout_persisted: boolean;
    execution_source: string;
  };
  safety: {
    arbitrary_code: boolean;
    arbitrary_sql: boolean;
    arbitrary_urls: boolean;
    workspace_mutation: boolean;
    i9_confirmation_required_for_future_mutations: boolean;
    background_execution_available: boolean;
    single_worker_v1: boolean;
  };
};

export type AutomationRun = {
  id: number;
  automation_id: number;
  status: string;
  trigger_source: string;
  event_id: number | null;
  dry_run: boolean;
  output: Record<string, unknown>;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
};
