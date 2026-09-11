"""I11 deterministic Ask LifeOS workspace coverage.

This layer answers common operational questions from authenticated LifeOS state
without asking an LLM to invent facts.  It intentionally reuses existing domain
services and ownership boundaries and returns a small, product-safe structure
that the Ask LifeOS UI can render consistently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable

from models import Document, DocumentAIAnalysis, Task
from services.module_service import list_owned_modules
from services.document_version_service import current_document_filter
from services.resource_limit_service import get_resource_limits
from services.project_review_agent_service import run_owned_portfolio_review_agent, run_owned_project_review_agent
from services.project_service import list_owned_projects
from services.task_service import build_tasks_overview
from services.workspace_context_service import _analysis_is_current, build_project_documents_context


MAX_I11_ITEMS = 12
COMPLETED_TASK_STATUS = "Completed"


@dataclass(frozen=True)
class WorkspaceInsightItem:
    item_type: str
    title: str
    detail: str
    severity: str = "normal"
    status: str | None = None
    deadline: str | None = None
    project_id: int | None = None
    project_title: str | None = None
    module_id: int | None = None
    module_title: str | None = None
    object_id: int | None = None
    source_type: str | None = None
    source_id: int | None = None
    action_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.item_type,
            "title": self.title,
            "detail": self.detail,
            "severity": self.severity,
            "status": self.status,
            "deadline": self.deadline,
            "project_id": self.project_id,
            "project_title": self.project_title,
            "module_id": self.module_id,
            "module_title": self.module_title,
            "object_id": self.object_id,
            "source": (
                {"type": self.source_type, "id": self.source_id}
                if self.source_type
                else None
            ),
            "action_hint": self.action_hint,
        }


@dataclass(frozen=True)
class WorkspaceInsightResult:
    kind: str
    summary: str
    items: tuple[WorkspaceInsightItem, ...]
    counts: dict[str, int]
    context_limited: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "items": [item.to_dict() for item in self.items],
            "counts": dict(self.counts),
            "context_limited": self.context_limited,
            "verified_from_state": True,
            "read_only": True,
        }


def _project_titles(owner_id: int) -> dict[int, str]:
    return {int(project.id): str(project.title) for project in list_owned_projects(owner_id)}


def _task_scope(owner_id: int, project_id: int | None) -> tuple[list[Task], dict[int, str]]:
    overview = build_tasks_overview(owner_id)
    tasks = list(overview.get("tasks") or [])
    if project_id is not None:
        tasks = [task for task in tasks if int(task.project_id or 0) == int(project_id)]
    projects = {int(project.id): str(project.title) for project in overview.get("projects") or []}
    return tasks, projects


def _priority_rank(value: Any) -> int:
    return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(str(value or "").casefold(), 0)


def _task_sort_key(task: Task, *, today: date) -> tuple[Any, ...]:
    deadline = task.deadline
    overdue = bool(deadline and deadline < today and task.status != COMPLETED_TASK_STATUS)
    blocked = str(task.status or "") == "Blocked"
    return (
        not blocked,
        not overdue,
        deadline is None,
        deadline or date.max,
        -_priority_rank(task.importance),
        -float(task.priority_score or 0),
        int(task.id or 0),
    )


def build_owned_task_status_insight(*, owner_id: int, query: str, project_id: int | None = None, today: date | None = None) -> WorkspaceInsightResult:
    effective_today = today or date.today()
    tasks, projects = _task_scope(owner_id, project_id)
    text = " ".join(str(query or "").casefold().split())
    open_tasks = [task for task in tasks if task.status != COMPLETED_TASK_STATUS]

    if "overdue" in text or "late" in text:
        kind = "overdue_tasks"
        selected = [task for task in open_tasks if task.deadline and task.deadline < effective_today]
        summary_prefix = "overdue"
    elif "blocked" in text:
        kind = "blocked_tasks"
        selected = [task for task in open_tasks if str(task.status or "") == "Blocked"]
        summary_prefix = "blocked"
    elif "due soon" in text or "next 7" in text or "this week" in text or "upcoming" in text:
        kind = "due_soon_tasks"
        limit = effective_today + timedelta(days=7)
        selected = [task for task in open_tasks if task.deadline and effective_today <= task.deadline <= limit]
        summary_prefix = "due in the next 7 days"
    else:
        kind = "task_status"
        selected = open_tasks
        summary_prefix = "open"

    selected.sort(key=lambda task: _task_sort_key(task, today=effective_today))
    limited = len(selected) > MAX_I11_ITEMS
    visible = selected[:MAX_I11_ITEMS]
    scope_label = projects.get(int(project_id)) if project_id is not None else None
    if visible:
        summary = f"I found {len(selected)} {summary_prefix} task{'s' if len(selected) != 1 else ''}"
        summary += f" in {scope_label}." if scope_label else " across your workspace."
    else:
        summary = f"I did not find any {summary_prefix} tasks"
        summary += f" in {scope_label}." if scope_label else " across your workspace."

    items = tuple(
        WorkspaceInsightItem(
            item_type="task",
            object_id=task.id,
            title=task.title,
            detail=(
                "Task is explicitly blocked."
                if task.status == "Blocked"
                else "Task is overdue."
                if task.deadline and task.deadline < effective_today
                else "Open task in LifeOS."
            ),
            severity=(
                "high" if task.status == "Blocked" or (task.deadline and task.deadline < effective_today)
                else "medium" if task.deadline and task.deadline <= effective_today + timedelta(days=3)
                else "normal"
            ),
            status=task.status,
            deadline=task.deadline.isoformat() if task.deadline else None,
            project_id=task.project_id,
            project_title=projects.get(int(task.project_id)) if task.project_id is not None else None,
            source_type="task",
            source_id=task.id,
            action_hint="Open the task and update its status, deadline, or next step.",
        )
        for task in visible
    )
    return WorkspaceInsightResult(
        kind=kind,
        summary=summary,
        items=items,
        counts={"matched": len(selected), "shown": len(items), "open": len(open_tasks)},
        context_limited=limited,
    )


def _deadline_window(query: str, today: date) -> tuple[date, str]:
    text = " ".join(str(query or "").casefold().split())
    if "today" in text:
        return today, "today"
    if "tomorrow" in text:
        return today + timedelta(days=1), "by tomorrow"
    if "this week" in text or "next 7" in text:
        return today + timedelta(days=7), "in the next 7 days"
    if "next 30" in text or "this month" in text:
        return today + timedelta(days=30), "in the next 30 days"
    return today + timedelta(days=14), "in the next 14 days"


def build_owned_deadline_insight(*, owner_id: int, query: str, project_id: int | None = None, today: date | None = None) -> WorkspaceInsightResult:
    effective_today = today or date.today()
    end_date, window_label = _deadline_window(query, effective_today)
    tasks, projects = _task_scope(owner_id, project_id)
    owned_projects = [project for project in list_owned_projects(owner_id) if project_id is None or int(project.id) == int(project_id)]

    rows: list[tuple[date, WorkspaceInsightItem]] = []
    for task in tasks:
        if task.status == COMPLETED_TASK_STATUS or not task.deadline:
            continue
        if task.deadline > end_date:
            continue
        overdue = task.deadline < effective_today
        rows.append((task.deadline, WorkspaceInsightItem(
            item_type="task_deadline",
            object_id=task.id,
            title=task.title,
            detail=("Task deadline has passed." if overdue else "Upcoming task deadline."),
            severity="high" if overdue else "medium" if task.deadline <= effective_today + timedelta(days=3) else "normal",
            status=task.status,
            deadline=task.deadline.isoformat(),
            project_id=task.project_id,
            project_title=projects.get(int(task.project_id)) if task.project_id is not None else None,
            source_type="task",
            source_id=task.id,
            action_hint="Review the task before its deadline.",
        )))

    for project in owned_projects:
        if not project.deadline or str(project.status or "").casefold() in {"completed", "complete", "archived"}:
            continue
        if project.deadline > end_date:
            continue
        overdue = project.deadline < effective_today
        rows.append((project.deadline, WorkspaceInsightItem(
            item_type="project_deadline",
            object_id=project.id,
            title=f"{project.title} project deadline",
            detail=("Project deadline has passed." if overdue else "Upcoming project deadline."),
            severity="high" if overdue else "medium" if project.deadline <= effective_today + timedelta(days=3) else "normal",
            status=project.status,
            deadline=project.deadline.isoformat(),
            project_id=project.id,
            project_title=project.title,
            source_type="project",
            source_id=project.id,
            action_hint="Review project progress and remaining tasks before the deadline.",
        )))

    rows.sort(key=lambda row: (row[0] >= effective_today, row[0], row[1].title.casefold()))
    limited = len(rows) > MAX_I11_ITEMS
    items = tuple(item for _, item in rows[:MAX_I11_ITEMS])
    if rows:
        summary = f"I found {len(rows)} deadline{'s' if len(rows) != 1 else ''} {window_label}, including anything already overdue."
    else:
        summary = f"I did not find an open task or project deadline {window_label}."
    return WorkspaceInsightResult(
        kind="upcoming_deadlines",
        summary=summary,
        items=items,
        counts={"matched": len(rows), "shown": len(items), "overdue": sum(1 for due, _ in rows if due < effective_today)},
        context_limited=limited,
    )


def _latest_completed_analyses(owner_id: int, document_ids: Iterable[int]) -> dict[int, list[DocumentAIAnalysis]]:
    ids = [int(value) for value in document_ids]
    if not ids:
        return {}
    rows = (
        DocumentAIAnalysis.query
        .filter(
            DocumentAIAnalysis.user_id == owner_id,
            DocumentAIAnalysis.document_id.in_(ids),
            DocumentAIAnalysis.status == "Completed",
        )
        .order_by(DocumentAIAnalysis.created_at.desc(), DocumentAIAnalysis.id.desc())
        .all()
    )
    grouped: dict[int, list[DocumentAIAnalysis]] = {doc_id: [] for doc_id in ids}
    for row in rows:
        grouped.setdefault(int(row.document_id), []).append(row)
    return grouped


def build_owned_document_review_insight(*, owner_id: int, project_id: int | None = None) -> WorkspaceInsightResult:
    projects = _project_titles(owner_id)
    if project_id is not None:
        docs, counts = build_project_documents_context(owner_id=owner_id, project_id=project_id)
        candidates = [doc for doc in docs if doc.get("analysis_status") in {"Stale", "Not analysed"}]
        items = tuple(
            WorkspaceInsightItem(
                item_type="document_review",
                object_id=int(doc["id"]),
                title=str(doc.get("filename") or "Document"),
                detail=(
                    "Saved structured analysis is stale and should be refreshed before relying on it."
                    if doc.get("analysis_status") == "Stale"
                    else "This current document has no completed structured analysis yet."
                ),
                severity="medium" if doc.get("analysis_status") == "Stale" else "normal",
                status=str(doc.get("analysis_status") or "Unknown"),
                project_id=project_id,
                project_title=projects.get(int(project_id)),
                source_type="document",
                source_id=int(doc["id"]),
                action_hint="Refresh analysis." if doc.get("analysis_status") == "Stale" else "Run document analysis.",
            )
            for doc in candidates[:MAX_I11_ITEMS]
        )
        total = len(candidates)
        limited = bool(counts.get("documents_limited")) or total > MAX_I11_ITEMS
    else:
        document_limit = get_resource_limits().max_scope_documents
        base_query = Document.query.filter(Document.user_id == owner_id, current_document_filter())
        total_current_documents = base_query.count()
        documents = (
            base_query
            .order_by(Document.uploaded_at.desc(), Document.id.desc())
            .limit(document_limit)
            .all()
        )
        analyses = _latest_completed_analyses(owner_id, [doc.id for doc in documents])
        rows: list[WorkspaceInsightItem] = []
        for document in documents:
            completed = analyses.get(int(document.id), [])
            current = next((analysis for analysis in completed if _analysis_is_current(document, analysis)), None)
            if current is not None:
                continue
            status = "Stale" if completed else "Not analysed"
            rows.append(WorkspaceInsightItem(
                item_type="document_review",
                object_id=document.id,
                title=document.filename,
                detail=(
                    "Saved structured analysis is stale and should be refreshed before relying on it."
                    if status == "Stale" else "This current document has no completed structured analysis yet."
                ),
                severity="medium" if status == "Stale" else "normal",
                status=status,
                project_id=document.project_id,
                project_title=projects.get(int(document.project_id)) if document.project_id is not None else None,
                source_type="document",
                source_id=document.id,
                action_hint="Refresh analysis." if status == "Stale" else "Run document analysis.",
            ))
        total = len(rows)
        limited = total_current_documents > len(documents) or total > MAX_I11_ITEMS
        items = tuple(rows[:MAX_I11_ITEMS])

    if total:
        stale = sum(1 for item in items if item.status == "Stale")
        summary = f"I found {total} current document{'s' if total != 1 else ''} that need analysis attention"
        if stale:
            summary += f", including {stale} stale analys{'es' if stale != 1 else 'is'}"
        summary += "."
    else:
        summary = "I did not find a current document with stale or missing structured analysis."
    return WorkspaceInsightResult(
        kind="documents_needing_review",
        summary=summary,
        items=items,
        counts={"matched": total, "shown": len(items), "stale_shown": sum(1 for item in items if item.status == "Stale")},
        context_limited=limited,
    )


def build_owned_workspace_gaps_insight(*, owner_id: int, project_id: int | None = None) -> WorkspaceInsightResult:
    if project_id is not None:
        agent = run_owned_project_review_agent(project_id=project_id, owner_id=owner_id)
        priorities = list(agent.priorities)
    else:
        agent = run_owned_portfolio_review_agent(owner_id=owner_id)
        priorities = list(agent.priorities)

    gap_categories = {"missing_information", "missing_next_action", "stale_document"}
    gaps = [priority for priority in priorities if priority.category in gap_categories]
    items = tuple(
        WorkspaceInsightItem(
            item_type="workspace_gap",
            title=priority.title,
            detail=priority.reason,
            severity=priority.severity,
            project_id=priority.project_id,
            project_title=priority.project_title,
            source_type=(priority.evidence[0].source_type if priority.evidence else None),
            source_id=(priority.evidence[0].source_id if priority.evidence else None),
            action_hint=priority.recommended_action,
        )
        for priority in gaps[:MAX_I11_ITEMS]
    )
    if items:
        summary = f"I found {len(gaps)} verified gap{'s' if len(gaps) != 1 else ''} in the current LifeOS state."
    else:
        summary = "I did not find a verified missing-information, stale-analysis, or missing-next-action gap in the reviewed state."
    return WorkspaceInsightResult(
        kind="workspace_gaps",
        summary=summary,
        items=items,
        counts={"matched": len(gaps), "shown": len(items)},
        context_limited=len(gaps) > MAX_I11_ITEMS or bool(getattr(agent, "context_limited", False)),
    )


def build_owned_study_next_insight(*, owner_id: int, today: date | None = None) -> WorkspaceInsightResult:
    effective_today = today or date.today()
    modules = [module for module in list_owned_modules(owner_id) if str(module.status or "Active") != "Archived"]
    candidates: list[tuple[int, date, int, WorkspaceInsightItem]] = []

    for module in modules:
        linked_tasks = list(module.task_links or [])
        task_by_lecture: dict[int | None, list[Task]] = {}
        for link in linked_tasks:
            task = getattr(link, "task", None)
            if task is None or task.status == COMPLETED_TASK_STATUS:
                continue
            task_by_lecture.setdefault(link.lecture_id, []).append(task)

        for lecture in list(module.lectures or []):
            if str(lecture.status or "") == "Completed":
                continue
            related_tasks = task_by_lecture.get(lecture.id, [])
            urgent_task = min((task.deadline for task in related_tasks if task.deadline), default=None)
            has_overdue = any(task.deadline and task.deadline < effective_today for task in related_tasks)
            has_due_soon = any(task.deadline and task.deadline <= effective_today + timedelta(days=7) for task in related_tasks)
            status_score = 80 if lecture.status == "In Progress" else 55
            score = 100 if has_overdue else 90 if has_due_soon else status_score
            order_date = urgent_task or lecture.lecture_date or date.max
            lecture_number = int(lecture.lecture_number or 999999)
            detail_parts = [f"{module.title} · {lecture.status or 'Planned'}"]
            if lecture.topics:
                topics = " ".join(str(lecture.topics).split())
                detail_parts.append(topics[:180] + ("…" if len(topics) > 180 else ""))
            if urgent_task:
                detail_parts.append(f"Linked task due {urgent_task.isoformat()}")
            candidates.append((
                -score,
                order_date,
                lecture_number,
                WorkspaceInsightItem(
                    item_type="study_next",
                    object_id=lecture.id,
                    title=(f"Lecture {lecture.lecture_number}: {lecture.title}" if lecture.lecture_number else lecture.title),
                    detail=" · ".join(detail_parts),
                    severity="high" if has_overdue else "medium" if has_due_soon or lecture.status == "In Progress" else "normal",
                    status=lecture.status,
                    deadline=urgent_task.isoformat() if urgent_task else (lecture.lecture_date.isoformat() if lecture.lecture_date else None),
                    module_id=module.id,
                    module_title=module.title,
                    source_type="lecture",
                    source_id=lecture.id,
                    action_hint="Continue this lecture and its linked study tasks." if lecture.status == "In Progress" else "Start this lecture next.",
                ),
            ))

    candidates.sort(key=lambda row: (row[0], row[1], row[2], row[3].module_title or "", row[3].title))
    items = tuple(row[3] for row in candidates[:MAX_I11_ITEMS])
    if items:
        summary = f"The clearest next study item is {items[0].title} in {items[0].module_title}."
    elif modules:
        summary = "Your active modules do not currently contain an unfinished lecture for LifeOS to rank."
    else:
        summary = "Create or activate a Module with lectures before LifeOS can recommend what to study next."
    return WorkspaceInsightResult(
        kind="study_next",
        summary=summary,
        items=items,
        counts={"active_modules": len(modules), "candidates": len(candidates), "shown": len(items)},
        context_limited=len(candidates) > MAX_I11_ITEMS,
    )


def build_owned_today_focus_insight(*, owner_id: int, project_id: int | None = None, today: date | None = None) -> WorkspaceInsightResult:
    effective_today = today or date.today()
    agent = (
        run_owned_project_review_agent(project_id=project_id, owner_id=owner_id, today=effective_today)
        if project_id is not None
        else run_owned_portfolio_review_agent(owner_id=owner_id, today=effective_today)
    )
    priorities = list(agent.priorities)
    items = tuple(
        WorkspaceInsightItem(
            item_type="today_focus",
            title=priority.title,
            detail=priority.reason,
            severity=priority.severity,
            project_id=priority.project_id,
            project_title=priority.project_title,
            source_type=(priority.evidence[0].source_type if priority.evidence else None),
            source_id=(priority.evidence[0].source_id if priority.evidence else None),
            action_hint=priority.recommended_action,
        )
        for priority in priorities[:5]
    )
    if items:
        summary = f"Your top focus today is {items[0].title}."
    else:
        summary = "LifeOS did not find a concrete blocked, overdue, near-deadline, stale-analysis, or next-action priority for today."
    return WorkspaceInsightResult(
        kind="today_focus",
        summary=summary,
        items=items,
        counts={"matched": len(priorities), "shown": len(items)},
        context_limited=bool(agent.context_limited) or len(priorities) > 5,
    )


def build_owned_project_question_insight(*, owner_id: int, project_id: int, query: str) -> WorkspaceInsightResult:
    project = next((item for item in list_owned_projects(owner_id) if int(item.id) == int(project_id)), None)
    if project is None:
        # Router ownership resolution should make this unreachable; fail closed.
        return WorkspaceInsightResult("project_fact", "The requested project is not available in your workspace.", (), {"matched": 0})

    text = " ".join(str(query or "").casefold().split())
    if "progress" in text:
        title, value, detail = "Saved project progress", f"{int(project.progress or 0)}%", "This is the manual project progress saved in LifeOS."
    elif "phase" in text:
        title, value, detail = "Current phase", str(project.current_phase or "Not set"), "Current project phase saved in LifeOS."
    elif "status" in text:
        title, value, detail = "Project status", str(project.status or "Not set"), "Current project status saved in LifeOS."
    elif "priority" in text:
        title, value, detail = "Project priority", str(project.priority or "Not set"), "Current project priority saved in LifeOS."
    elif "goal" in text:
        title, value, detail = "Project goal", str(project.goal or "Not set"), "Current project goal saved in LifeOS."
    elif "start" in text:
        title, value, detail = "Project start date", project.start_date.isoformat() if project.start_date else "Not set", "Current project start date saved in LifeOS."
    elif "deadline" in text or "due" in text:
        title, value, detail = "Project deadline", project.deadline.isoformat() if project.deadline else "Not set", "Current project deadline saved in LifeOS."
    else:
        title, value, detail = "Project state", f"{project.status or 'Not set'} · {int(project.progress or 0)}%", "Current status and saved progress from LifeOS."

    item = WorkspaceInsightItem(
        item_type="project_fact",
        object_id=project.id,
        title=title,
        detail=f"{value}. {detail}",
        project_id=project.id,
        project_title=project.title,
        status=project.status,
        deadline=project.deadline.isoformat() if project.deadline else None,
        source_type="project",
        source_id=project.id,
    )
    return WorkspaceInsightResult(
        kind="project_fact",
        summary=f"{project.title}: {title.lower()} is {value}.",
        items=(item,),
        counts={"matched": 1, "shown": 1},
    )
