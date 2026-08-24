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
