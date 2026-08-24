import { apiDelete, apiGet, apiPatch, apiPost } from "../../api/client";
import type { Project, ProjectInput, ProjectListData, ProjectWorkspaceData } from "../../api/types";

export const projectKeys = {
  all: ["projects"] as const,
  detail: (id: number) => ["projects", id] as const,
};

export function fetchProjects() {
  return apiGet<ProjectListData>("/api/v1/projects");
}

export function fetchProject(id: number) {
  return apiGet<ProjectWorkspaceData>(`/api/v1/projects/${id}`);
}

export function createProject(input: ProjectInput) {
  return apiPost<{ item: Project }>("/api/v1/projects", input);
}

export function updateProject(id: number, input: Partial<ProjectInput>) {
  return apiPatch<{ item: Project }>(`/api/v1/projects/${id}`, input);
}

export function deleteProject(id: number) {
  return apiDelete<{ deleted: boolean; title: string }>(`/api/v1/projects/${id}`);
}
