"""Step 18 — objective RAG evaluation for LifeOS Document Brain.

The evaluator deliberately reuses the production retrieval and grounded Q&A
workflows. It does not introduce another RAG implementation. Gold cases describe
what evidence and facts should be found; the runner measures retrieval, answer
and citation behavior and can fail CI when a baseline regresses.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from database import db
from models import (
    Document,
    DocumentCollection,
    DocumentCollectionItem,
    DocumentCollectionQuestion,
    DocumentQuestion,
    LearningModule,
    Lecture,
    ModuleQuestion,
    Project,
    ProjectQuestion,
)
from services.document_collection_question_workflow_service import (
    ask_owned_collection_documents,
)
from services.document_collection_retrieval_service import (
    retrieve_owned_collection_chunks,
)
from services.document_hybrid_retrieval_service import (
    retrieve_owned_document_chunks_hybrid,
)
from services.document_question_workflow_service import ask_owned_document
from services.document_scope_retrieval_service import retrieve_owned_document_set
from services.document_version_service import current_document_filter
from services.module_question_workflow_service import (
    ask_owned_module_documents,
    list_owned_module_scope_documents,
)
from services.project_document_retrieval_service import (
    retrieve_owned_project_document_chunks,
)
from services.project_question_workflow_service import ask_owned_project_documents
from services.rag_evaluation_metrics import (
    answer_text_checks,
    mean,
    source_expectation_metrics,
)


DATASET_VERSION = 1
DEFAULT_TOP_K = 10
MAX_TOP_K = 12
VALID_MODES = {"retrieval", "full"}


class RagEvaluationError(RuntimeError):
    """Base error for Step 18 evaluation."""


class RagEvaluationDatasetError(RagEvaluationError):
    """Raised when a gold dataset is malformed."""


class RagEvaluationScopeError(RagEvaluationError):
    """Raised when a gold case cannot resolve an owned runtime scope."""


@dataclass(frozen=True)
class ResolvedScope:
    scope_type: str
    scope_id: int
    label: str
    document: Document | None = None
    project: Project | None = None
    collection: DocumentCollection | None = None
    module: LearningModule | None = None
    lecture: Lecture | None = None


def load_rag_evaluation_dataset(path: str | Path) -> dict[str, Any]:
    dataset_path = Path(path)
    if not dataset_path.is_file():
        raise RagEvaluationDatasetError(f"Evaluation dataset not found: {dataset_path}")

    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RagEvaluationDatasetError(
            f"Could not read evaluation dataset: {dataset_path}"
        ) from error

    if not isinstance(payload, dict):
        raise RagEvaluationDatasetError("Evaluation dataset root must be an object.")
    if int(payload.get("version") or 0) != DATASET_VERSION:
        raise RagEvaluationDatasetError(
            f"Evaluation dataset version must be {DATASET_VERSION}."
        )

    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise RagEvaluationDatasetError("Evaluation dataset must contain at least one case.")

    seen_ids: set[str] = set()
    for index, case in enumerate(cases, start=1):
        _validate_case(case, index=index)
        case_id = str(case["id"])
        if case_id in seen_ids:
            raise RagEvaluationDatasetError(f"Duplicate evaluation case id: {case_id}")
        seen_ids.add(case_id)

    thresholds = payload.get("thresholds") or {}
    if not isinstance(thresholds, dict):
        raise RagEvaluationDatasetError("thresholds must be an object when supplied.")

    return payload


def run_rag_evaluation(
    *,
    dataset_path: str | Path,
    user_id: int,
    mode: str = "retrieval",
    top_k: int | None = None,
) -> dict[str, Any]:
    """Run a gold dataset against the current authoritative LifeOS RAG paths."""

    cleaned_mode = str(mode or "retrieval").strip().lower()
    if cleaned_mode not in VALID_MODES:
        raise RagEvaluationError(
            f"Evaluation mode must be one of: {', '.join(sorted(VALID_MODES))}."
        )

    dataset = load_rag_evaluation_dataset(dataset_path)
    effective_top_k = _validate_top_k(
        top_k if top_k is not None else (dataset.get("defaults") or {}).get("top_k", DEFAULT_TOP_K)
    )

    started_at = datetime.utcnow()
    case_results: list[dict[str, Any]] = []

    for case in dataset["cases"]:
        case_results.append(
            _run_case(
                case=case,
                user_id=int(user_id),
                mode=cleaned_mode,
                top_k=effective_top_k,
            )
        )

    summary = _build_summary(case_results)
    threshold_results = _evaluate_thresholds(
        thresholds=dataset.get("thresholds") or {},
        summary=summary,
        mode=cleaned_mode,
    )
    overall_pass = (
        summary["error_cases"] == 0
        and summary["failed_cases"] == 0
        and all(item["passed"] for item in threshold_results)
    )

    return {
        "step": 18,
        "dataset_version": DATASET_VERSION,
        "dataset_name": str(dataset.get("name") or Path(dataset_path).stem),
        "dataset_path": str(Path(dataset_path)),
        "mode": cleaned_mode,
        "user_id": int(user_id),
        "top_k": effective_top_k,
        "started_at": started_at.isoformat(timespec="seconds") + "Z",
        "completed_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "summary": summary,
        "threshold_results": threshold_results,
        "passed": overall_pass,
        "cases": case_results,
    }


def write_rag_evaluation_report(report: dict[str, Any], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return output_path


def format_rag_evaluation_summary(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        f"Step 18 RAG Evaluation — {report.get('dataset_name', 'dataset')}",
        f"mode={report.get('mode')} top_k={report.get('top_k')} user_id={report.get('user_id')}",
        (
            "cases="
            f"{summary.get('total_cases', 0)} "
            f"passed={summary.get('passed_cases', 0)} "
            f"failed={summary.get('failed_cases', 0)} "
            f"errors={summary.get('error_cases', 0)} "
            f"skipped={summary.get('skipped_cases', 0)}"
        ),
    ]

    if summary.get("retrieval_recall_mean") is not None:
        lines.append(
            "retrieval: "
            f"mean_recall={_format_metric(summary.get('retrieval_recall_mean'))} "
            f"all_sources_rate={_format_metric(summary.get('retrieval_all_sources_rate'))} "
            f"mrr={_format_metric(summary.get('retrieval_mrr'))}"
        )

    if report.get("mode") == "full" and summary.get("answerability_accuracy") is not None:
        lines.append(
            "answers: "
            f"answerability_accuracy={_format_metric(summary.get('answerability_accuracy'))} "
            f"answer_text_accuracy={_format_metric(summary.get('answer_text_accuracy'))} "
            f"citation_recall={_format_metric(summary.get('citation_recall_mean'))}"
        )

    for threshold in report.get("threshold_results") or []:
        marker = "PASS" if threshold.get("passed") else "FAIL"
        lines.append(
            f"threshold {threshold.get('metric')}: {marker} "
            f"actual={threshold.get('actual')} required={threshold.get('minimum')}"
        )

    lines.append("RESULT: PASS" if report.get("passed") else "RESULT: FAIL")
    return "\n".join(lines)


def _format_metric(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.3f}"


def _run_case(
    *,
    case: dict[str, Any],
    user_id: int,
    mode: str,
    top_k: int,
) -> dict[str, Any]:
    case_id = str(case["id"])
    question = str(case["question"]).strip()
    expected = case.get("expected") or {}

    result: dict[str, Any] = {
        "id": case_id,
        "description": str(case.get("description") or ""),
        "tags": list(case.get("tags") or []),
        "scope": dict(case["scope"]),
        "question": question,
        "status": "error",
        "passed": False,
        "error": None,
        "retrieval": None,
        "answer": None,
    }

    try:
        resolved = _resolve_scope(case["scope"], user_id=user_id)
        sources = _retrieve_sources(
            resolved=resolved,
            user_id=user_id,
            question=question,
            top_k=top_k,
        )
        retrieval_metrics = source_expectation_metrics(
            expected_sources=expected.get("retrieval_sources") or expected.get("sources") or [],
            actual_sources=sources,
        )
        result["resolved_scope"] = {
            "type": resolved.scope_type,
            "id": resolved.scope_id,
            "label": resolved.label,
            "lecture_id": resolved.lecture.id if resolved.lecture is not None else None,
        }
        result["retrieval"] = {
            "source_count": len(sources),
            "sources": sources,
            **retrieval_metrics,
        }

        retrieval_pass = (
            bool(retrieval_metrics["all_expected_found"])
            if retrieval_metrics["applicable"]
            else True
        )

        if mode == "retrieval":
            # Cases that only test grounding/answer text need the answerability
            # verifier and are explicitly skipped in retrieval-only mode.
            answer_only = (
                not retrieval_metrics["applicable"]
                and (
                    "answerable" in expected
                    or bool(expected.get("answer_contains"))
                    or bool(expected.get("answer_not_contains"))
                    or bool(expected.get("citation_sources"))
                )
            )
            if answer_only:
                result["status"] = "skipped"
                result["passed"] = True
            else:
                result["status"] = "passed" if retrieval_pass else "failed"
                result["passed"] = retrieval_pass
            return result

        answer_result = _run_answer(
            resolved=resolved,
            user_id=user_id,
            question=question,
        )
        answerable_expected = expected.get("answerable")
        answerable_actual = bool(answer_result["sources"])
        answerability_applicable = isinstance(answerable_expected, bool)
        answerability_correct = (
            answerable_actual == answerable_expected
            if answerability_applicable
            else True
        )

        text_metrics = answer_text_checks(
            answer=answer_result["answer"],
            required=expected.get("answer_contains") or [],
            forbidden=expected.get("answer_not_contains") or [],
        )
        citation_metrics = source_expectation_metrics(
            expected_sources=expected.get("citation_sources") or expected.get("sources") or [],
            actual_sources=answer_result["sources"],
        )
        citation_pass = (
            bool(citation_metrics["all_expected_found"])
            if citation_metrics["applicable"]
            else True
        )

        result["answer"] = {
            "answer": answer_result["answer"],
            "provider": answer_result.get("provider"),
            "model": answer_result.get("model"),
            "answerable_actual": answerable_actual,
            "answerable_expected": answerable_expected,
            "answerability_applicable": answerability_applicable,
            "answerability_correct": answerability_correct,
            "text": text_metrics,
            "citation": citation_metrics,
            "sources": answer_result["sources"],
        }

        case_pass = (
            retrieval_pass
            and answerability_correct
            and bool(text_metrics["passed"])
            and citation_pass
        )
        result["status"] = "passed" if case_pass else "failed"
        result["passed"] = case_pass
        return result

    except Exception as error:  # evaluator must report a broken case, not hide it
        result["error"] = f"{error.__class__.__name__}: {error}"
        result["status"] = "error"
        result["passed"] = False
        return result


def _resolve_scope(scope: dict[str, Any], *, user_id: int) -> ResolvedScope:
    scope_type = str(scope.get("type") or "").strip().lower()

    if scope_type == "document":
        candidates = Document.query.filter(
            Document.user_id == user_id,
            current_document_filter(),
        )
        if scope.get("id") is not None:
            candidates = candidates.filter(Document.id == int(scope["id"]))
        elif str(scope.get("filename") or "").strip():
            candidates = candidates.filter(Document.filename == str(scope["filename"]).strip())
        else:
            raise RagEvaluationScopeError("Document scope requires id or filename.")
        document = _unique(candidates.all(), "document")
        return ResolvedScope(
            scope_type="document",
            scope_id=document.id,
            label=document.filename,
            document=document,
        )

    if scope_type == "project":
        query = Project.query.filter(Project.user_id == user_id)
        if scope.get("id") is not None:
            query = query.filter(Project.id == int(scope["id"]))
        elif str(scope.get("title") or "").strip():
            query = query.filter(Project.title == str(scope["title"]).strip())
        else:
            raise RagEvaluationScopeError("Project scope requires id or title.")
        project = _unique(query.all(), "project")
        return ResolvedScope("project", project.id, project.title, project=project)

    if scope_type == "collection":
        collection = _resolve_collection(scope, user_id=user_id)
        return ResolvedScope(
            "collection", collection.id, collection.name, collection=collection
        )

    if scope_type in {"module", "lecture"}:
        module_query = LearningModule.query.filter(LearningModule.user_id == user_id)
        if scope.get("id") is not None:
            module_query = module_query.filter(LearningModule.id == int(scope["id"]))
        elif str(scope.get("title") or "").strip():
            module_query = module_query.filter(
                LearningModule.title == str(scope["title"]).strip()
            )
        else:
            raise RagEvaluationScopeError("Module scope requires id or title.")
        module = _unique(module_query.all(), "module")

        lecture = None
        lecture_selector = scope.get("lecture")
        if scope_type == "lecture" or lecture_selector:
            selector = lecture_selector if isinstance(lecture_selector, dict) else scope
            lecture_query = Lecture.query.filter(Lecture.module_id == module.id)
            if selector.get("id") is not None:
                lecture_query = lecture_query.filter(Lecture.id == int(selector["id"]))
            elif selector.get("number") is not None:
                lecture_query = lecture_query.filter(
                    Lecture.lecture_number == int(selector["number"])
                )
            elif str(selector.get("title") or "").strip():
                lecture_query = lecture_query.filter(
                    Lecture.title == str(selector["title"]).strip()
                )
            else:
                raise RagEvaluationScopeError(
                    "Lecture scope requires lecture id, number, or title."
                )
            lecture = _unique(lecture_query.all(), "lecture")

        label = f"{module.title} / {lecture.title}" if lecture is not None else module.title
        return ResolvedScope(
            scope_type="lecture" if lecture is not None else "module",
            scope_id=module.id,
            label=label,
            module=module,
            lecture=lecture,
        )

    raise RagEvaluationScopeError(
        "Unsupported scope type. Use document, project, collection, module, or lecture."
    )


def _resolve_collection(scope: dict[str, Any], *, user_id: int) -> DocumentCollection:
    query = DocumentCollection.query.filter(DocumentCollection.user_id == user_id)
    if scope.get("id") is not None:
        return _unique(query.filter(DocumentCollection.id == int(scope["id"])).all(), "collection")
    if str(scope.get("name") or "").strip():
        return _unique(
            query.filter(DocumentCollection.name == str(scope["name"]).strip()).all(),
            "collection",
        )

    filenames = {
        str(item).strip().casefold()
        for item in (scope.get("document_filenames") or [])
        if str(item).strip()
    }
    if not filenames:
        raise RagEvaluationScopeError(
            "Collection scope requires id, name, or document_filenames."
        )

    matches: list[DocumentCollection] = []
    for collection in query.order_by(DocumentCollection.id.asc()).all():
        documents = (
            Document.query
            .join(
                DocumentCollectionItem,
                DocumentCollectionItem.document_id == Document.id,
            )
            .filter(
                DocumentCollectionItem.collection_id == collection.id,
                Document.user_id == user_id,
                current_document_filter(),
            )
            .all()
        )
        available = {str(item.filename or "").strip().casefold() for item in documents}
        if filenames.issubset(available):
            matches.append(collection)

    return _unique(matches, "collection matching document_filenames")


def _retrieve_sources(
    *,
    resolved: ResolvedScope,
    user_id: int,
    question: str,
    top_k: int,
) -> list[dict[str, Any]]:
    if resolved.scope_type == "document":
        retrieval = retrieve_owned_document_chunks_hybrid(
            document_id=resolved.document.id,
            user_id=user_id,
            query=question,
            limit=top_k,
        )
        return [
            {
                "rank": rank,
                "document_id": retrieval.document.id,
                "filename": retrieval.document.filename,
                "page": item.source().get("page"),
                "section": item.source().get("section"),
                "evidence": item.source().get("evidence"),
                "content_type": item.source().get("content_type", "text"),
                "table_id": item.source().get("table_id"),
                "chunk_id": item.chunk.id,
                "chunk_index": item.chunk.chunk_index,
                "score": item.score,
                "keyword_score": item.keyword_score,
                "semantic_score": item.semantic_score,
                "retrieval_methods": list(item.retrieval_methods),
            }
            for rank, item in enumerate(retrieval.chunks, start=1)
        ]

    if resolved.scope_type == "project":
        retrieval = retrieve_owned_project_document_chunks(
            project_id=resolved.project.id,
            user_id=user_id,
            query=question,
            limit=top_k,
        )
        return [
            _ranked_source(rank, item.source(), item.retrieved)
            for rank, item in enumerate(retrieval.chunks, start=1)
        ]

    if resolved.scope_type == "collection":
        retrieval = retrieve_owned_collection_chunks(
            collection_id=resolved.collection.id,
            user_id=user_id,
            query=question,
            limit=top_k,
        )
        return [
            _ranked_source(rank, item.source(), item.retrieved)
            for rank, item in enumerate(retrieval.chunks, start=1)
        ]

    if resolved.scope_type in {"module", "lecture"}:
        documents = list_owned_module_scope_documents(
            module_id=resolved.module.id,
            user_id=user_id,
            lecture_id=resolved.lecture.id if resolved.lecture is not None else None,
        )
        retrieval = retrieve_owned_document_set(
            documents=documents,
            user_id=user_id,
            query=question,
            limit=top_k,
            visibility="lecture_owner" if resolved.lecture is not None else "module_owner",
        )
        return [
            _ranked_source(rank, item.source(), item.retrieved)
            for rank, item in enumerate(retrieval.chunks, start=1)
        ]

    raise RagEvaluationScopeError(f"Cannot retrieve scope type: {resolved.scope_type}")


def _ranked_source(rank: int, source: dict[str, Any], retrieved: Any) -> dict[str, Any]:
    return {
        "rank": rank,
        "document_id": source.get("document_id"),
        "filename": source.get("filename"),
        "page": source.get("page"),
        "section": source.get("section"),
        "evidence": source.get("evidence"),
        "content_type": source.get("content_type", "text"),
        "table_id": source.get("table_id"),
        "chunk_id": source.get("chunk_id"),
        "chunk_index": source.get("chunk_index"),
        "score": getattr(retrieved, "score", None),
        "keyword_score": getattr(retrieved, "keyword_score", None),
        "semantic_score": getattr(retrieved, "semantic_score", None),
        "retrieval_methods": list(getattr(retrieved, "retrieval_methods", ()) or ()),
    }


def _run_answer(
    *,
    resolved: ResolvedScope,
    user_id: int,
    question: str,
) -> dict[str, Any]:
    started_at = datetime.utcnow() - timedelta(seconds=1)
    saved = None
    try:
        if resolved.scope_type == "document":
            saved = ask_owned_document(
                document_id=resolved.document.id,
                user_id=user_id,
                question_text=question,
                force=True,
            )
        elif resolved.scope_type == "project":
            saved = ask_owned_project_documents(
                project_id=resolved.project.id,
                user_id=user_id,
                question_text=question,
                force=True,
            )
        elif resolved.scope_type == "collection":
            saved = ask_owned_collection_documents(
                collection_id=resolved.collection.id,
                user_id=user_id,
                question_text=question,
                force=True,
            )
        elif resolved.scope_type in {"module", "lecture"}:
            saved = ask_owned_module_documents(
                module_id=resolved.module.id,
                lecture_id=resolved.lecture.id if resolved.lecture is not None else None,
                user_id=user_id,
                question_text=question,
                force=True,
            )
        else:
            raise RagEvaluationScopeError(f"Cannot answer scope type: {resolved.scope_type}")

        row = saved.question
        sources = [dict(item) for item in (row.sources or [])]
        if resolved.scope_type == "document":
            for source in sources:
                source.setdefault("document_id", resolved.document.id)
                source.setdefault("filename", resolved.document.filename)

        return {
            "answer": str(row.answer or ""),
            "sources": sources,
            "provider": str(row.provider or ""),
            "model": str(row.model or ""),
        }
    finally:
        # Full evaluation intentionally exercises the real persistence workflow,
        # then removes only the evaluation-created question row so the user's Q&A
        # history is not polluted. Chunk/embedding caches remain reusable.
        if saved is not None:
            try:
                db.session.delete(saved.question)
                db.session.commit()
            except Exception:
                db.session.rollback()
        else:
            _cleanup_failed_evaluation_rows(
                resolved=resolved,
                user_id=user_id,
                question=question,
                started_at=started_at,
            )


def _cleanup_failed_evaluation_rows(
    *,
    resolved: ResolvedScope,
    user_id: int,
    question: str,
    started_at: datetime,
) -> None:
    try:
        if resolved.scope_type == "document":
            model = DocumentQuestion
            query = model.query.filter_by(
                document_id=resolved.document.id,
                user_id=user_id,
                question=question,
            )
        elif resolved.scope_type == "project":
            model = ProjectQuestion
            query = model.query.filter_by(
                project_id=resolved.project.id,
                user_id=user_id,
                question=question,
            )
        elif resolved.scope_type == "collection":
            model = DocumentCollectionQuestion
            query = model.query.filter_by(
                collection_id=resolved.collection.id,
                user_id=user_id,
                question=question,
            )
        else:
            model = ModuleQuestion
            query = model.query.filter_by(
                module_id=resolved.module.id,
                lecture_id=resolved.lecture.id if resolved.lecture is not None else None,
                user_id=user_id,
                question=question,
            )

        for row in query.filter(model.created_at >= started_at).all():
            db.session.delete(row)
        db.session.commit()
    except Exception:
        db.session.rollback()


def _build_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    retrieval_metrics = [
        item["retrieval"]
        for item in cases
        if item.get("retrieval") and item["retrieval"].get("applicable")
    ]
    answered = [item["answer"] for item in cases if item.get("answer") is not None]

    answerability_values = [
        1.0 if item.get("answerability_correct") else 0.0
        for item in answered
        if item.get("answerability_applicable")
    ]
    text_values = [
        1.0 if item["text"].get("passed") else 0.0
        for item in answered
        if item.get("text", {}).get("applicable")
    ]
    citation_metrics = [
        item["citation"]
        for item in answered
        if item.get("citation", {}).get("applicable")
    ]

    return {
        "total_cases": len(cases),
        "passed_cases": sum(item.get("status") == "passed" for item in cases),
        "failed_cases": sum(item.get("status") == "failed" for item in cases),
        "error_cases": sum(item.get("status") == "error" for item in cases),
        "skipped_cases": sum(item.get("status") == "skipped" for item in cases),
        "retrieval_cases": len(retrieval_metrics),
        "retrieval_recall_mean": mean(item.get("recall") for item in retrieval_metrics),
        "retrieval_all_sources_rate": mean(
            1.0 if item.get("all_expected_found") else 0.0 for item in retrieval_metrics
        ),
        "retrieval_mrr": mean(item.get("reciprocal_rank") for item in retrieval_metrics),
        "full_answer_cases": len(answered),
        "answerability_accuracy": mean(answerability_values),
        "answer_text_accuracy": mean(text_values),
        "citation_recall_mean": mean(item.get("recall") for item in citation_metrics),
        "citation_all_sources_rate": mean(
            1.0 if item.get("all_expected_found") else 0.0 for item in citation_metrics
        ),
    }


def _evaluate_thresholds(
    *,
    thresholds: dict[str, Any],
    summary: dict[str, Any],
    mode: str,
) -> list[dict[str, Any]]:
    aliases = {
        "retrieval_recall": "retrieval_recall_mean",
        "retrieval_all_sources_rate": "retrieval_all_sources_rate",
        "retrieval_mrr": "retrieval_mrr",
        "answerability_accuracy": "answerability_accuracy",
        "answer_text_accuracy": "answer_text_accuracy",
        "citation_recall": "citation_recall_mean",
        "citation_all_sources_rate": "citation_all_sources_rate",
    }
    full_only = {
        "answerability_accuracy",
        "answer_text_accuracy",
        "citation_recall",
        "citation_all_sources_rate",
    }

    results = []
    for name, raw_minimum in thresholds.items():
        if name not in aliases:
            continue
        if mode != "full" and name in full_only:
            continue
        try:
            minimum = float(raw_minimum)
        except (TypeError, ValueError):
            raise RagEvaluationDatasetError(f"Threshold {name} must be numeric.")
        if minimum < 0.0 or minimum > 1.0:
            raise RagEvaluationDatasetError(
                f"Threshold {name} must be between 0.0 and 1.0."
            )
        actual = summary.get(aliases[name])
        passed = actual is not None and float(actual) >= minimum
        results.append(
            {
                "metric": name,
                "minimum": minimum,
                "actual": actual,
                "passed": passed,
            }
        )
    return results


def _validate_case(case: Any, *, index: int) -> None:
    if not isinstance(case, dict):
        raise RagEvaluationDatasetError(f"Case {index} must be an object.")
    if not str(case.get("id") or "").strip():
        raise RagEvaluationDatasetError(f"Case {index} requires an id.")
    if not str(case.get("question") or "").strip():
        raise RagEvaluationDatasetError(f"Case {case.get('id')} requires a question.")
    if not isinstance(case.get("scope"), dict):
        raise RagEvaluationDatasetError(f"Case {case.get('id')} requires a scope object.")
    if not str(case["scope"].get("type") or "").strip():
        raise RagEvaluationDatasetError(f"Case {case.get('id')} scope requires a type.")
    expected = case.get("expected") or {}
    if not isinstance(expected, dict):
        raise RagEvaluationDatasetError(f"Case {case.get('id')} expected must be an object.")
    if "answerable" in expected and not isinstance(expected["answerable"], bool):
        raise RagEvaluationDatasetError(
            f"Case {case.get('id')} expected.answerable must be true or false."
        )
    for key in (
        "sources",
        "retrieval_sources",
        "citation_sources",
        "answer_contains",
        "answer_not_contains",
    ):
        if key in expected and not isinstance(expected[key], list):
            raise RagEvaluationDatasetError(
                f"Case {case.get('id')} expected.{key} must be a list."
            )

    for key in ("sources", "retrieval_sources", "citation_sources"):
        for source in expected.get(key) or []:
            if not isinstance(source, dict):
                raise RagEvaluationDatasetError(
                    f"Case {case.get('id')} expected.{key} entries must be objects."
                )


def _validate_top_k(value: Any) -> int:
    try:
        cleaned = int(value)
    except (TypeError, ValueError) as error:
        raise RagEvaluationError("top_k must be an integer.") from error
    if cleaned < 1 or cleaned > MAX_TOP_K:
        raise RagEvaluationError(f"top_k must be between 1 and {MAX_TOP_K}.")
    return cleaned


def _unique(items: list[Any], label: str):
    if not items:
        raise RagEvaluationScopeError(f"Owned {label} was not found.")
    if len(items) > 1:
        raise RagEvaluationScopeError(
            f"Gold scope is ambiguous: more than one owned {label} matched. Use an id."
        )
    return items[0]
