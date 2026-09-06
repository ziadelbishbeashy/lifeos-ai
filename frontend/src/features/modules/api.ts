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

export function createModuleAssessment(moduleId: number, input: Record<string, unknown>) {
  return apiPost<{ item: import("../../api/types").ModuleAssessment }>(`/api/v1/modules/${moduleId}/assessments`, input);
}

export function updateModuleAssessment(moduleId: number, assessmentId: number, input: Record<string, unknown>) {
  return apiPatch<{ item: import("../../api/types").ModuleAssessment }>(`/api/v1/modules/${moduleId}/assessments/${assessmentId}`, input);
}

export function deleteModuleAssessment(moduleId: number, assessmentId: number) {
  return apiDelete<{ deleted: boolean; title: string }>(`/api/v1/modules/${moduleId}/assessments/${assessmentId}`);
}

export function importAcademicSchedule(file: File) {
  const form = new FormData();
  form.append("document", file);
  return apiPostForm<{ document: { id: number; filename: string; original_upload_name: string }; proposals: import("../../api/types").AssessmentImportProposal[] }>("/api/v1/modules/assessment-imports", form);
}

export function fetchAssessmentImportProposals(sourceDocumentId?: number) {
  const query = sourceDocumentId ? `?source_document_id=${sourceDocumentId}` : "";
  return apiGet<{ proposals: import("../../api/types").AssessmentImportProposal[] }>(`/api/v1/modules/assessment-proposals${query}`);
}

export function updateAssessmentImportProposal(proposalId: number, input: Record<string, unknown>) {
  return apiPatch<{ proposal: import("../../api/types").AssessmentImportProposal }>(`/api/v1/modules/assessment-proposals/${proposalId}`, input);
}

export function dismissAssessmentImportProposal(proposalId: number) {
  return apiPost<{ proposal: import("../../api/types").AssessmentImportProposal }>(`/api/v1/modules/assessment-proposals/${proposalId}/dismiss`, {});
}

export function confirmSelectedAssessmentImportProposals(proposalIds: number[]) {
  return apiPost<{ confirmed: import("../../api/types").AssessmentImportProposal[]; failed: Array<{ id: number; message: string }>; changed: boolean }>("/api/v1/modules/assessment-proposals/confirm-selected", { proposal_ids: proposalIds });
}
