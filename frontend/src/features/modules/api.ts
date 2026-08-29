import { apiDelete, apiGet, apiPatch, apiPost, apiPostForm } from "../../api/client";
import type { LearningModule, LearningModuleDetail, ModuleDetailData, ModuleQuestion } from "../../api/types";

export const moduleKeys = {
  all: ["modules"] as const,
  detail: (id: number) => ["modules", id] as const,
};

export function fetchModules() {
  return apiGet<{ items: LearningModule[] }>("/api/v1/modules");
}

export function fetchModule(id: number) {
  return apiGet<ModuleDetailData>(`/api/v1/modules/${id}`);
}

export function createModule(input: { title: string; subject?: string; description?: string }) {
  return apiPost<{ item: LearningModuleDetail }>("/api/v1/modules", input);
}

export function updateModule(id: number, input: Partial<{ title: string; subject: string; description: string; status: string }>) {
  return apiPatch<{ item: LearningModuleDetail }>(`/api/v1/modules/${id}`, input);
}

export function deleteModule(id: number) {
  return apiDelete<{ deleted: boolean; title: string }>(`/api/v1/modules/${id}`);
}

export function createLecture(moduleId: number, input: { title: string; lecture_number?: number | null; lecture_date?: string; status?: string; topics?: string; summary?: string }) {
  return apiPost<{ item: LearningModuleDetail }>(`/api/v1/modules/${moduleId}/lectures`, input);
}

export function updateLecture(moduleId: number, lectureId: number, input: Record<string, unknown>) {
  return apiPatch<{ item: LearningModuleDetail }>(`/api/v1/modules/${moduleId}/lectures/${lectureId}`, input);
}

export function deleteLecture(moduleId: number, lectureId: number) {
  return apiDelete<{ deleted: boolean; title: string; item: LearningModuleDetail }>(`/api/v1/modules/${moduleId}/lectures/${lectureId}`);
}

export function linkModuleDocument(moduleId: number, documentId: number, lectureId?: number | null) {
  return apiPost<{ item: LearningModuleDetail }>(`/api/v1/modules/${moduleId}/documents`, { document_id: documentId, lecture_id: lectureId ?? null });
}

export function uploadModuleDocument(moduleId: number, file: File, lectureId?: number | null) {
  const form = new FormData();
  form.append("document", file);
  if (lectureId) form.append("lecture_id", String(lectureId));
  return apiPostForm<{ item: LearningModuleDetail }>(`/api/v1/modules/${moduleId}/documents/upload`, form);
}

export function unlinkModuleDocument(moduleId: number, documentId: number) {
  return apiDelete<{ removed: boolean; item: LearningModuleDetail }>(`/api/v1/modules/${moduleId}/documents/${documentId}`);
}

function resourcePath(kind: "notes" | "tasks" | "collections") {
  return kind;
}

export function linkModuleResource(moduleId: number, kind: "notes" | "tasks" | "collections", resourceId: number, lectureId?: number | null) {
  const singular = kind === "notes" ? "note" : kind === "tasks" ? "task" : "collection";
  return apiPost<{ item: LearningModuleDetail }>(`/api/v1/modules/${moduleId}/${resourcePath(kind)}`, {
    [`${singular}_id`]: resourceId,
    ...(kind !== "collections" ? { lecture_id: lectureId ?? null } : {}),
  });
}

export function unlinkModuleResource(moduleId: number, kind: "notes" | "tasks" | "collections", resourceId: number) {
  return apiDelete<{ removed: boolean; item: LearningModuleDetail }>(`/api/v1/modules/${moduleId}/${resourcePath(kind)}/${resourceId}`);
}

export function askModule(moduleId: number, question: string, lectureId?: number | null) {
  return apiPost<{ item: ModuleQuestion; reused_existing: boolean }>(`/api/v1/modules/${moduleId}/questions`, {
    question,
    lecture_id: lectureId ?? null,
  });
}
