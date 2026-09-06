"""I21.2 intelligent academic schedule import.

One owned PDF/photo can yield many confirmation-gated assessment proposals across
existing modules.  Document Brain remains the evidence authority; I9 remains the
mutation boundary; ModuleAssessment remains accepted workspace truth only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any

from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from database import db
from models import DocumentChunk, LearningModule, LifeOSActionProposal, ModuleAssessment
from services.academic_schedule_ai_service import AcademicScheduleAIError, AcademicScheduleAIValidationError, extract_academic_schedule_items
from services.document_access_service import DocumentNotFoundError, require_owned_document
from services.document_hybrid_retrieval_service import DocumentHybridRetrievalError, retrieve_owned_document_chunks_hybrid
from services.document_ocr_workflow_service import DocumentOCRWorkflowError, process_owned_document_ocr
from services.document_service import CreatedProjectDocument, DocumentUploadError, create_project_pdf_document
from services.module_assessment_service import ASSESSMENT_TYPES, ModuleAssessmentValidationError, validate_module_assessment_payload
from services.module_service import ModuleNotFoundError, require_owned_module
from storage.base import StorageService


ACTION_CREATE_MODULE_ASSESSMENT = "create_module_assessment"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
PDF_MIME_TYPES = {"application/pdf", "application/x-pdf"}
RETRIEVAL_QUERIES = (
    "final exam timetable examination schedule course date time",
    "quiz midterm assessment schedule course module date time",
    "assignment coursework deadline due submission weight percentage",
    "project presentation lab assessment date deadline weighting",
)


class ModuleAssessmentImportError(RuntimeError):
    pass


class ModuleAssessmentImportValidationError(ModuleAssessmentImportError, ValueError):
    pass


class ModuleAssessmentImportNotFoundError(ModuleAssessmentImportError, LookupError):
    pass


@dataclass(frozen=True)
class AcademicScheduleImportResult:
    document_id: int
    document_filename: str
    original_upload_name: str
    proposals: tuple[LifeOSActionProposal, ...]


def _normalized_words(value: Any) -> list[str]:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    return [word for word in text.split() if word]


def _module_match_score(source: str, module: LearningModule) -> float:
    source_words = _normalized_words(source)
    if not source_words:
        return 0.0
    source_norm = " ".join(source_words)
    title_norm = " ".join(_normalized_words(module.title))
    subject_norm = " ".join(_normalized_words(module.subject))
    if not title_norm:
        return 0.0
    if title_norm == source_norm:
        return 1.0
    if title_norm in source_norm or source_norm in title_norm:
        return 0.96
    source_set, title_set = set(source_words), set(title_norm.split())
    overlap = len(source_set & title_set) / max(1, len(title_set))
    ratio = SequenceMatcher(None, source_norm, title_norm).ratio()
    subject_bonus = 0.08 if subject_norm and (subject_norm in source_norm or source_norm in subject_norm) else 0.0
    return min(1.0, max(overlap, ratio) + subject_bonus)


def _resolve_module(candidate: dict[str, Any], modules: list[LearningModule]) -> tuple[int | None, str, float]:
    source = str(candidate.get("module_text") or "").strip()
    ai_module_id = candidate.get("module_id")
    ranked = sorted(((module, _module_match_score(source, module)) for module in modules), key=lambda item: item[1], reverse=True)
    if ranked and ranked[0][1] >= 0.88:
        return ranked[0][0].id, "high", ranked[0][1]
    if ranked and ranked[0][1] >= 0.68 and (len(ranked) == 1 or ranked[0][1] - ranked[1][1] >= 0.12):
        return ranked[0][0].id, "medium", ranked[0][1]
    if ai_module_id is not None:
        for module in modules:
            if module.id == int(ai_module_id):
                confidence = str(candidate.get("module_match_confidence") or "low").lower()
                return module.id, confidence if confidence in {"high", "medium", "low"} else "low", ranked[0][1] if ranked else 0.0
    return None, "low", ranked[0][1] if ranked else 0.0


def _image_to_pdf_upload(upload: FileStorage, *, max_bytes: int) -> tuple[FileStorage, str]:
    original_name = secure_filename(upload.filename or "schedule") or "schedule"
    raw = upload.stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ModuleAssessmentImportValidationError("The academic schedule file is too large.")
    if not raw:
        raise ModuleAssessmentImportValidationError("Choose a non-empty timetable image.")
    try:
        image = Image.open(BytesIO(raw))
        image.verify()
        image = Image.open(BytesIO(raw))
        if image.mode not in {"RGB", "L"}:
            background = Image.new("RGB", image.size, "white")
            if "A" in image.getbands():
                background.paste(image, mask=image.getchannel("A"))
            else:
                background.paste(image.convert("RGB"))
            image = background
        else:
            image = image.convert("RGB")
        output = BytesIO()
        image.save(output, format="PDF", resolution=150.0)
        output.seek(0)
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ModuleAssessmentImportValidationError("LifeOS could not read that timetable image.") from error
    stem = Path(original_name).stem[:180] or "schedule"
    normalized_name = f"{stem}-schedule-import.pdf"
    return FileStorage(stream=output, filename=normalized_name, content_type="application/pdf"), original_name


def _prepare_upload(upload: FileStorage | None, *, max_bytes: int) -> tuple[FileStorage, str]:
    if upload is None or not str(upload.filename or "").strip():
        raise ModuleAssessmentImportValidationError("Choose an exam timetable, screenshot, photo, or PDF.")
    original = secure_filename(upload.filename or "schedule") or "schedule"
    suffix = Path(original).suffix.lower()
    content_type = str(upload.mimetype or "").lower()
    if suffix == ".pdf" or content_type in PDF_MIME_TYPES:
        return upload, original
    if suffix in IMAGE_EXTENSIONS or content_type in IMAGE_MIME_TYPES:
        return _image_to_pdf_upload(upload, max_bytes=max_bytes)
    raise ModuleAssessmentImportValidationError("Academic schedule import accepts PDF, PNG, JPG, JPEG, or WebP files.")


def _ensure_searchable(uploaded: CreatedProjectDocument, *, user_id: int) -> None:
    document = uploaded.document
    if document.ocr_status == "pending" or not str(document.extracted_text or "").strip():
        try:
            process_owned_document_ocr(document_id=document.id, user_id=user_id, force=False)
        except DocumentOCRWorkflowError as error:
            raise ModuleAssessmentImportError(f"LifeOS could not read the timetable with OCR: {error}") from error
        db.session.expire_all()
        document = require_owned_document(document.id, user_id)
    if not str(document.extracted_text or "").strip() and not list(getattr(document, "tables", []) or []):
        raise ModuleAssessmentImportValidationError("LifeOS could not find readable schedule text in that file.")


def _evidence_catalog(*, document_id: int, user_id: int) -> list[dict[str, Any]]:
    by_chunk: dict[int, Any] = {}
    for query in RETRIEVAL_QUERIES:
        try:
            result = retrieve_owned_document_chunks_hybrid(document_id=document_id, user_id=user_id, query=query, limit=12)
        except DocumentHybridRetrievalError:
            continue
        for retrieved in result.chunks:
            if retrieved.chunk.id is not None:
                by_chunk.setdefault(int(retrieved.chunk.id), retrieved)
    if not by_chunk:
        document = require_owned_document(document_id, user_id)
        for chunk in list(document.chunks or [])[:20]:
            by_chunk[int(chunk.id)] = type("FallbackRetrieved", (), {"chunk": chunk, "source": lambda self, c=chunk: {
                "page": c.page_start or c.page_end, "section": c.section_title, "evidence": str(c.text or "")[:900],
                "content_type": str(getattr(c, "content_type", "text") or "text"), "table_id": getattr(c, "table_id", None),
            }})()
    catalog: list[dict[str, Any]] = []
    for position, retrieved in enumerate(by_chunk.values(), start=1):
        source = retrieved.source()
        catalog.append({
            "id": f"e{position}",
            "document_id": document_id,
            "chunk_id": int(retrieved.chunk.id),
            "page": source.get("page"),
            "section": source.get("section"),
            "content_type": source.get("content_type"),
            "table_id": source.get("table_id"),
            "excerpt": source.get("evidence") or str(retrieved.chunk.text or "")[:900],
        })
    return catalog


def _duplicate_for_payload(payload: dict[str, Any], *, user_id: int) -> ModuleAssessment | None:
    module_id = payload.get("module_id")
    if not module_id:
        return None
    require_owned_module(int(module_id), user_id)
    title_key = " ".join(_normalized_words(payload.get("title")))
    kind = str(payload.get("assessment_type") or "")
    target = payload.get("due_date") if kind == "Assignment" else payload.get("assessment_date")
    target = target or payload.get("assessment_date") or payload.get("due_date")
    for assessment in ModuleAssessment.query.filter_by(module_id=int(module_id)).all():
        existing_key = " ".join(_normalized_words(assessment.title))
        existing_target = assessment.due_date if assessment.assessment_type == "Assignment" else assessment.assessment_date
        existing_target = existing_target or assessment.assessment_date or assessment.due_date
        same_date = bool(target and existing_target and str(existing_target) == str(target))
        title_ratio = SequenceMatcher(None, title_key, existing_key).ratio() if title_key and existing_key else 0.0
        if (same_date and title_ratio >= 0.55) or (title_ratio >= 0.92 and kind == assessment.assessment_type):
            return assessment
    return None


def _review_state(payload: dict[str, Any], *, confidence: str, module_confidence: str, duplicate: ModuleAssessment | None) -> str:
    if payload.get("module_id") is None:
        return "needs_module"
    if duplicate is not None:
        return "possible_duplicate"
    target = payload.get("due_date") if payload.get("assessment_type") == "Assignment" else payload.get("assessment_date")
    target = target or payload.get("assessment_date") or payload.get("due_date")
    if payload.get("validation_issues") or confidence != "high" or module_confidence == "low" or not target:
        return "needs_review"
    return "ready"


def _proposal_payload(candidate: dict[str, Any], *, module_id: int | None, source_document_id: int, source_filename: str, original_upload_name: str) -> dict[str, Any]:
    base = {
        "title": candidate.get("title"),
        "assessment_type": candidate.get("assessment_type"),
        "status": "Upcoming",
    }
    # Title/type are required proposal identity. Optional AI-extracted values are
    # validated independently so one malformed field becomes reviewable/null
    # rather than poisoning the whole schedule import.
    normalized_base = validate_module_assessment_payload(base)
    normalized: dict[str, Any] = dict(normalized_base)
    issues: list[str] = []
    for field in ("assessment_date", "assessment_time", "due_date", "due_time", "weight_percent", "topics", "estimated_study_minutes", "notes"):
        value = candidate.get(field)
        if value in (None, ""):
            normalized[field] = None
            continue
        try:
            checked = validate_module_assessment_payload({**base, field: value})
            normalized[field] = checked.get(field)
        except ModuleAssessmentValidationError as error:
            normalized[field] = None
            issues.append(str(error))

    payload = {
        "module_id": module_id,
        **{key: normalized.get(key) for key in (
            "title", "assessment_type", "assessment_date", "assessment_time", "due_date", "due_time",
            "weight_percent", "status", "topics", "estimated_study_minutes", "notes",
        )},
        "source_document_id": source_document_id,
        "source_document_filename": source_filename,
        "source_original_upload_name": original_upload_name,
        "source_module_text": candidate.get("module_text"),
        "extraction_confidence": candidate.get("confidence"),
        "module_match_confidence": candidate.get("module_match_confidence"),
        "validation_issues": issues,
    }
    return payload


def import_academic_schedule_upload(*, upload: FileStorage | None, user_id: int, max_bytes: int, storage: StorageService | None = None) -> AcademicScheduleImportResult:
    prepared, original_name = _prepare_upload(upload, max_bytes=max_bytes)
    try:
        uploaded = create_project_pdf_document(prepared, owner_id=user_id, project_id=None, max_bytes=max_bytes, storage=storage)
    except (DocumentUploadError, ValueError) as error:
        raise ModuleAssessmentImportError(str(error)) from error
    _ensure_searchable(uploaded, user_id=user_id)
    document = require_owned_document(uploaded.document.id, user_id)
    evidence_catalog = _evidence_catalog(document_id=document.id, user_id=user_id)
    if not evidence_catalog:
        raise ModuleAssessmentImportValidationError("LifeOS could not locate assessment schedule evidence in that document.")

    modules = LearningModule.query.filter_by(user_id=user_id).order_by(LearningModule.title.asc()).all()
    if not modules:
        raise ModuleAssessmentImportValidationError("Create your modules before importing an academic schedule.")
    module_catalog = [{"id": item.id, "title": item.title, "subject": item.subject} for item in modules]
    try:
        candidates = extract_academic_schedule_items(evidence_catalog=evidence_catalog, modules=module_catalog, current_year=date.today().year)
    except (AcademicScheduleAIError, AcademicScheduleAIValidationError) as error:
        raise ModuleAssessmentImportError(str(error)) from error
    if not candidates:
        raise ModuleAssessmentImportValidationError("LifeOS did not find any supported assessments in that schedule.")

    evidence_by_id = {item["id"]: item for item in evidence_catalog}
    proposals: list[LifeOSActionProposal] = []
    for candidate in candidates:
        module_id, module_confidence, match_score = _resolve_module(candidate, modules)
        candidate["module_match_confidence"] = module_confidence
        payload = _proposal_payload(candidate, module_id=module_id, source_document_id=document.id, source_filename=document.filename, original_upload_name=original_name)
        duplicate = _duplicate_for_payload(payload, user_id=user_id) if module_id else None
        payload["review_state"] = _review_state(payload, confidence=str(candidate.get("confidence") or "low"), module_confidence=module_confidence, duplicate=duplicate)
        payload["module_match_score"] = round(float(match_score), 3)
        payload["duplicate_assessment_id"] = duplicate.id if duplicate is not None else None
        evidence = [dict(evidence_by_id[item_id], source_filename=document.filename, original_upload_name=original_name) for item_id in candidate.get("evidence_ids", []) if item_id in evidence_by_id]
        proposal = LifeOSActionProposal(
            user_id=user_id,
            action_type=ACTION_CREATE_MODULE_ASSESSMENT,
            status="pending",
            title=f"Import assessment: {payload['title']}"[:255],
            reason="Extracted from an uploaded academic schedule and waiting for your review.",
            target_type="module",
            target_id=module_id,
            project_id=None,
            payload_json=json.dumps(payload, ensure_ascii=False),
            evidence_json=json.dumps(evidence, ensure_ascii=False),
            risk_level="medium",
            requires_confirmation=True,
        )
        db.session.add(proposal)
        proposals.append(proposal)
    try:
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise ModuleAssessmentImportError("LifeOS could not save the academic schedule proposals.") from error
    return AcademicScheduleImportResult(document_id=document.id, document_filename=document.filename, original_upload_name=original_name, proposals=tuple(proposals))


def list_owned_assessment_import_proposals(*, user_id: int, source_document_id: int | None = None) -> list[LifeOSActionProposal]:
    query = LifeOSActionProposal.query.filter_by(user_id=user_id, action_type=ACTION_CREATE_MODULE_ASSESSMENT)
    rows = query.order_by(LifeOSActionProposal.created_at.desc(), LifeOSActionProposal.id.desc()).limit(100).all()
    if source_document_id is None:
        return rows
    return [row for row in rows if int(row.payload.get("source_document_id") or 0) == int(source_document_id)]


def update_owned_assessment_import_proposal(*, proposal_id: int, user_id: int, changes: dict[str, Any]) -> LifeOSActionProposal:
    proposal = LifeOSActionProposal.query.filter_by(id=proposal_id, user_id=user_id, action_type=ACTION_CREATE_MODULE_ASSESSMENT).first()
    if proposal is None:
        raise ModuleAssessmentImportNotFoundError("Assessment proposal not found.")
    if proposal.status != "pending":
        raise ModuleAssessmentImportValidationError("Only pending assessment proposals can be edited.")
    allowed = {"module_id", "title", "assessment_type", "assessment_date", "assessment_time", "due_date", "due_time", "weight_percent", "topics", "estimated_study_minutes", "notes"}
    unknown = set(changes) - allowed
    if unknown:
        raise ModuleAssessmentImportValidationError(f"Unsupported proposal fields: {', '.join(sorted(unknown))}.")
    payload = dict(proposal.payload)
    for key in allowed & set(changes):
        payload[key] = changes.get(key)
    module_id = payload.get("module_id")
    if module_id in (None, "", 0, "0"):
        module_id = None
    else:
        try:
            module_id = int(module_id)
        except (TypeError, ValueError) as error:
            raise ModuleAssessmentImportValidationError("Select a valid module.") from error
        try:
            require_owned_module(module_id, user_id)
        except ModuleNotFoundError as error:
            raise ModuleAssessmentImportValidationError("Select a module from your workspace.") from error
    payload["module_id"] = module_id
    try:
        normalized = validate_module_assessment_payload({key: payload.get(key) for key in (
            "title", "assessment_type", "assessment_date", "assessment_time", "due_date", "due_time",
            "weight_percent", "status", "topics", "estimated_study_minutes", "notes",
        )})
    except ModuleAssessmentValidationError as error:
        raise ModuleAssessmentImportValidationError(str(error)) from error
    payload.update(normalized)
    # Any malformed extracted field has now either been corrected by the user or
    # normalized successfully, so stale extraction validation warnings must not
    # keep the proposal permanently marked as needing review.
    payload["validation_issues"] = []
    duplicate = _duplicate_for_payload(payload, user_id=user_id) if module_id else None
    payload["duplicate_assessment_id"] = duplicate.id if duplicate is not None else None
    payload["review_state"] = _review_state(payload, confidence=str(payload.get("extraction_confidence") or "low"), module_confidence="high" if module_id else "low", duplicate=duplicate)
    proposal.target_id = module_id
    proposal.payload_json = json.dumps(payload, ensure_ascii=False)
    proposal.title = f"Import assessment: {payload['title']}"[:255]
    try:
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise ModuleAssessmentImportError("LifeOS could not update the assessment proposal.") from error
    return proposal


def assessment_proposal_duplicate(*, proposal: LifeOSActionProposal, user_id: int) -> ModuleAssessment | None:
    if proposal.action_type != ACTION_CREATE_MODULE_ASSESSMENT:
        return None
    return _duplicate_for_payload(proposal.payload, user_id=user_id)


def validate_assessment_proposal_evidence(*, proposal: LifeOSActionProposal, user_id: int) -> None:
    """Revalidate immutable source provenance before an I9 assessment write."""
    if proposal.action_type != ACTION_CREATE_MODULE_ASSESSMENT:
        raise ModuleAssessmentImportValidationError("This is not an academic assessment proposal.")
    payload = proposal.payload
    try:
        source_document_id = int(payload.get("source_document_id"))
    except (TypeError, ValueError) as error:
        raise ModuleAssessmentImportValidationError("The assessment proposal has no valid source document.") from error
    require_owned_document(source_document_id, user_id)
    evidence = proposal.evidence
    if not evidence:
        raise ModuleAssessmentImportValidationError("The assessment proposal has no retained source evidence.")
    chunk_ids: set[int] = set()
    for item in evidence:
        if not isinstance(item, dict):
            raise ModuleAssessmentImportValidationError("The assessment proposal contains invalid source evidence.")
        try:
            evidence_document_id = int(item.get("document_id"))
            chunk_id = int(item.get("chunk_id"))
        except (TypeError, ValueError) as error:
            raise ModuleAssessmentImportValidationError("The assessment proposal contains invalid source evidence.") from error
        if evidence_document_id != source_document_id:
            raise ModuleAssessmentImportValidationError("The assessment evidence no longer matches its source document.")
        chunk_ids.add(chunk_id)
    owned_chunk_ids = {
        int(row.id)
        for row in DocumentChunk.query.filter(
            DocumentChunk.document_id == source_document_id,
            DocumentChunk.user_id == user_id,
            DocumentChunk.id.in_(chunk_ids),
        ).all()
    }
    if owned_chunk_ids != chunk_ids:
        raise ModuleAssessmentImportValidationError("Some assessment evidence is no longer available in the source document.")
