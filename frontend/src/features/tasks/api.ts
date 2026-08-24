import { apiDelete, apiGet, apiPatch, apiPost } from "../../api/client";
import type { Task, TaskInput, TaskListData } from "../../api/types";

export const taskKeys = {
  all: ["tasks"] as const,
  detail: (id: number) => ["tasks", id] as const,
};

export function fetchTasks() {
  return apiGet<TaskListData>("/api/v1/tasks");
}

export function createTask(input: TaskInput) {
  return apiPost<{ item: Task }>("/api/v1/tasks", input);
}

export function updateTask(id: number, input: Partial<TaskInput>) {
  return apiPatch<{ item: Task }>(`/api/v1/tasks/${id}`, input);
}

export function toggleTask(id: number) {
  return apiPost<{ item: Task; message: string }>(`/api/v1/tasks/${id}/toggle`);
}

export function deleteTask(id: number) {
  return apiDelete<{ deleted: boolean; title: string; project_id: number | null }>(
    `/api/v1/tasks/${id}`,
  );
}
