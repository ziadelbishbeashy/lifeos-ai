"""Deterministic I3 intent + scope routing for Ask LifeOS.

The first router does not let an LLM choose database IDs or arbitrary tools.
It classifies a small reviewed intent set and resolves project targets only from
projects already owned by the authenticated user.  Low-confidence/ambiguous
requests fail into clarification instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any

from services.project_service import list_owned_projects


MAX_INTELLIGENCE_QUERY_CHARACTERS = 1200


class IntelligenceRouterError(ValueError):
    """Raised for invalid natural-language router input."""


@dataclass(frozen=True)
class ScopeCandidate:
    scope_type: str
    scope_id: int
    label: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.scope_type,
            "id": self.scope_id,
            "label": self.label,
            "confidence": round(float(self.confidence), 3),
        }


@dataclass(frozen=True)
class IntelligenceRouteDecision:
    query: str
    intent: str
    confidence: float
    scope_type: str | None
    scope_id: int | None
    scope_label: str | None
    status: str
    requires_clarification: bool
    clarification: str | None
    candidates: tuple[ScopeCandidate, ...]
    router_version: str = "deterministic-router-v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "intent": self.intent,
            "confidence": round(float(self.confidence), 3),
            "scope": (
                {
                    "type": self.scope_type,
                    "id": self.scope_id,
                    "label": self.scope_label,
                }
                if self.scope_type and self.scope_label
                else None
            ),
            "status": self.status,
            "requires_clarification": self.requires_clarification,
            "clarification": self.clarification,
            "candidates": [item.to_dict() for item in self.candidates],
            "router_version": self.router_version,
            "read_only": True,
        }


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().replace("’", "'")
    text = re.sub(r"[^a-z0-9+#._' -]+", " ", text)
    return " ".join(text.split())


def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _project_candidates(*, owner_id: int, normalized_query: str) -> tuple[ScopeCandidate, ...]:
    projects = list_owned_projects(owner_id)
    matches: list[ScopeCandidate] = []

    numeric_match = re.search(r"\bproject\s+#?(\d+)\b", normalized_query)
    if numeric_match:
        requested_id = int(numeric_match.group(1))
        for project in projects:
            if int(project.id) == requested_id:
                return (
                    ScopeCandidate("project", project.id, project.title, 1.0),
                )
        # Do not reveal whether an unowned project ID exists.
        return ()

    for project in projects:
        title = str(project.title or "").strip()
        normalized_title = _normalize(title)
        if not normalized_title:
            continue

        if normalized_title in normalized_query:
            matches.append(ScopeCandidate("project", project.id, title, 0.99))
            continue

        query_tokens = set(normalized_query.split())
        title_tokens = set(normalized_title.split())
        token_coverage = (
            len(query_tokens & title_tokens) / len(title_tokens)
            if title_tokens
            else 0.0
        )
        similarity = SequenceMatcher(None, normalized_title, normalized_query).ratio()
        score = max(token_coverage * 0.9, similarity * 0.72)
        if score >= 0.72:
            matches.append(ScopeCandidate("project", project.id, title, score))

    matches.sort(key=lambda item: (-item.confidence, item.label.casefold(), item.scope_id))
    return tuple(matches[:5])


def _classify_intent(text: str, *, project_resolved: bool) -> tuple[str, float]:
    # I16 memory queries are explicit and inspectable. Keep them ahead of
    # memory-candidate detection so questions such as "What do I prefer?" never
    # become save proposals.
    if _has_any(text, (
        "what do you remember", "what have you remembered", "what do you know about my preferences",
        "what are my saved preferences", "show my memory", "show lifeos memory",
        "lifeos memory", "what have i told you to remember", "what are you remembering",
        "how do i prefer", "what do i prefer", "what is my preference", "what's my preference",
        "how should you review", "how should you answer", "my project review preference",
    )):
        return "memory_query", 0.99

    # I16.1 conversational memory: statements such as "I prefer..." are not
    # silently persisted. They route to a confirmation proposal instead.
    if _has_any(text, (
        "remember that", "remember this", "please remember", "keep in mind",
        "i prefer", "i'd prefer", "i would prefer", "my preference is",
        "i want you to always", "from now on", "when you review", "when you answer",
        "my current focus", "i am focusing on", "i'm focusing on", "my focus is",
        "right now i am working on", "right now i'm working on",
    )):
        return "memory_candidate", 0.99

    # I13 relationship questions are more specific than task/document/project
    # status language. Route them into the verified context graph before broad
    # object handlers claim words such as "task" or "document".
    if _has_any(text, (
        "what is connected to", "what's connected to", "what is linked to", "what's linked to",
        "connected context", "related to this", "linked to this",
        "why does this task exist", "why does the task exist", "why does task",
        "where did this task come from", "where did the task come from",
        "which document is this task based on", "which document is the task based on",
        "which document is task", "which file is task", "task based on",
        "tasks came from", "tasks come from", "tasks created from",
        "notes related to", "documents related to", "source of this task",
        "trace this task", "trace this document", "trace this note", "show connections for",
    )):
        return "context_connections", 0.99

    # I11 operational intents are checked before the broad review/focus phrases
    # so everyday questions get a deterministic executor instead of falling
    # through to a generic project review.
    if _has_any(text, (
        "what should i do today", "what do i do today", "what should i focus on today",
        "what should i focus today", "today's focus", "todays focus", "plan my day",
        "what needs attention today", "what is my focus today",
    )):
        return "today_focus", 0.99

    if _has_any(text, (
        "what should i study next", "what do i study next", "what should i learn next",
        "what lecture should i do next", "which lecture next", "next lecture",
        "what should i revise next", "what should i review next for study",
    )):
        return "study_next", 0.98

    if _has_any(text, (
        "documents need review", "document needs review", "documents need attention",
        "document needs attention", "which documents", "which pdfs", "stale documents",
        "stale analysis", "documents are stale", "documents without analysis",
        "documents need analysis", "pdfs need review",
    )):
        return "document_review", 0.97

    if _has_any(text, (
        "what am i missing", "what are we missing", "what is missing", "what's missing",
        "missing information", "missing next action", "gaps in my project", "project gaps",
        "what am i overlooking", "anything missing",
    )):
        return "workspace_gaps", 0.96

    if _has_any(text, (
        "upcoming deadline", "upcoming deadlines", "deadline coming", "deadlines coming",
        "what deadlines", "which deadlines", "deadlines this week", "deadline this week",
        "due dates", "what is due", "what's due", "what is coming up",
    )):
        return "deadline_review", 0.96

    # Task-state language is more specific than broad portfolio phrases such as
    # "all my projects". Keep this ahead of portfolio review/focus so queries
    # like "Which tasks are overdue across all my projects?" preserve the
    # task_status executor while the scope resolver independently chooses the
    # portfolio.
    if _has_any(text, (
        "overdue", "blocked task", "blocked tasks", "due soon", "my tasks",
        "task status", "tasks due", "open tasks",
    )):
        return "task_status", 0.94

    focus_phrases = (
        "what should i focus",
        "what i should focus",
        "should i focus",
        "focus on first",
        "what should i work on",
        "what needs my attention",
        "what needs attention",
        "tell me what needs attention",
        "which project needs attention",
        "which projects need attention",
        "what should i do next",
        "what do i do next",
        "next priority",
        "top priority",
        "prioritize",
        "prioritise",
        "tell me what to focus",
        "where should i focus",
    )
    portfolio_markers = (
        "all my projects",
        "all projects",
        "every project",
        "all of my projects",
        "across my projects",
        "which project should i focus",
        "which projects should i focus",
    )
    if _has_any(text, focus_phrases) and _has_any(text, portfolio_markers):
        return "portfolio_focus", 0.98

    if _has_any(text, ("what changed", "recent activity", "recent updates", "what's new", "what is new")):
        return "recent_activity", 0.94

    portfolio_review_phrases = (
        "all my projects",
        "all projects",
        "every project",
        "my projects going",
        "how are my projects",
        "review my projects",
        "review all projects",
        "which projects need attention",
    )
    if _has_any(text, portfolio_review_phrases):
        return "portfolio_review", 0.97

    if _has_any(text, focus_phrases):
        return "project_focus", 0.97 if project_resolved else 0.88

    project_review_phrases = (
        "review my project",
        "review this project",
        "review the project",
        "review project",
        "how is my",
        "how's my",
        "how is the project",
        "how is this project",
        "how is project",
        "project health",
        "how is it going",
        "how's it going",
    )
    if _has_any(text, project_review_phrases) or (
        project_resolved
        and _has_any(text, ("review", "going", "health", "attention", "focus on"))
    ):
        return "project_review", 0.96 if project_resolved else 0.86

    if _has_any(text, (
        "project deadline", "project priority", "project goal", "project phase",
        "project progress", "project status", "project start date",
    )):
        return "project_question", 0.93 if project_resolved else 0.86

    if project_resolved and _has_any(
        text,
        (
            "deadline",
            "priority",
            "goal",
            "current phase",
            "phase",
            "progress",
            "status",
            "start date",
        ),
    ):
        return "project_question", 0.91

    if _has_any(text, ("lecture", "module", "course")):
        return "module_question", 0.78

    if _has_any(text, ("document", "pdf", "file says", "in the file")):
        return "document_question", 0.78

    if _has_any(text, ("find", "search", "look for", "where did", "where is", "which document")):
        return "knowledge_search", 0.75

    if project_resolved:
        return "project_question", 0.72

    return "general_conversation", 0.55

def route_intelligence_request(*, query: str, owner_id: int, continuation_intent: str | None = None, forced_project_id: int | None = None) -> IntelligenceRouteDecision:
    raw_query = str(query or "").strip()
    if not raw_query:
        raise IntelligenceRouterError("Ask LifeOS needs a question or request.")
    if len(raw_query) > MAX_INTELLIGENCE_QUERY_CHARACTERS:
        raise IntelligenceRouterError(
            f"Ask LifeOS requests must be {MAX_INTELLIGENCE_QUERY_CHARACTERS} characters or fewer."
        )

    normalized_query = _normalize(raw_query)
    candidates = _project_candidates(owner_id=int(owner_id), normalized_query=normalized_query)
    resolved = candidates[0] if candidates else None
    owned_projects = list_owned_projects(int(owner_id))

    # An explicit context-picker project is stronger than fuzzy language. It is
    # still resolved only from the authenticated owner's projects.
    if forced_project_id is not None:
        selected_project = next(
            (item for item in owned_projects if int(item.id) == int(forced_project_id)),
            None,
        )
        if selected_project is None:
            raise IntelligenceRouterError("The selected LifeOS project is not available.")
        resolved = ScopeCandidate("project", selected_project.id, selected_project.title, 1.0)
        candidates = (resolved,)

    continuation = str(continuation_intent or "").strip()
    all_project_reply = normalized_query in {
        "all", "all of them", "all projects", "all my projects", "every project", "every one"
    }
    if continuation in {
        "project_review", "project_focus", "recent_activity", "task_status", "deadline_review",
        "document_review", "workspace_gaps", "project_question", "today_focus",
    } and all_project_reply:
        portfolio_intent = (
            "portfolio_focus" if continuation == "project_focus"
            else "portfolio_review" if continuation in {"project_review", "project_question"}
            else continuation
        )
        return IntelligenceRouteDecision(
            query=raw_query,
            intent=portfolio_intent,
            confidence=0.99,
            scope_type="portfolio",
            scope_id=None,
            scope_label="All projects",
            status="ready",
            requires_clarification=False,
            clarification=None,
            candidates=(),
        )

    # Treat near-tied fuzzy candidates as ambiguous. Exact title matches (0.99)
    # naturally win unless the user explicitly named more than one project.
    if len(candidates) >= 2 and abs(candidates[0].confidence - candidates[1].confidence) < 0.08:
        resolved = None

    generic_project_reference = _has_any(
        normalized_query,
        ("my project", "this project", "the project"),
    )
    if resolved is None and generic_project_reference and len(owned_projects) == 1:
        project = owned_projects[0]
        resolved = ScopeCandidate("project", project.id, project.title, 0.84)
        candidates = (resolved,)

    intent, confidence = _classify_intent(
        normalized_query,
        project_resolved=resolved is not None,
    )
    if continuation in {
        "project_review", "project_focus", "recent_activity", "task_status", "deadline_review",
        "document_review", "workspace_gaps", "project_question", "today_focus",
    } and resolved is not None:
        intent, confidence = continuation, 0.98

    project_required = intent in {"project_review", "project_focus", "project_question"}
    project_word_present = "project" in normalized_query
    explicit_all_projects = _has_any(
        normalized_query,
        ("all projects", "all my projects", "all of my projects", "every project", "across my projects"),
    )
    activity_all_projects = intent == "recent_activity" and explicit_all_projects
    requires_clarification = False
    clarification = None

    if project_required and resolved is None:
        requires_clarification = True
        if candidates:
            names = ", ".join(item.label for item in candidates[:3])
            clarification = f"Which project do you mean: {names}?"
        elif owned_projects:
            clarification = "Which LifeOS project should I use?"
            candidates = tuple(
                ScopeCandidate("project", project.id, project.title, 0.5)
                for project in owned_projects[:5]
            )
        else:
            clarification = "Create a project first, then I can review its state."
    elif intent not in {"portfolio_review", "portfolio_focus"} and not activity_all_projects and not explicit_all_projects and project_word_present and resolved is None and len(owned_projects) > 1:
        requires_clarification = True
        clarification = "Which LifeOS project do you mean?"

    if requires_clarification:
        status = "clarification_required"
    elif intent in {"project_review", "project_focus"} and resolved is not None:
        status = "ready"
    elif intent in {
        "portfolio_review", "portfolio_focus", "recent_activity", "task_status",
        "deadline_review", "document_review", "workspace_gaps", "study_next",
        "today_focus", "project_question", "memory_query", "memory_candidate",
    }:
        status = "ready"
    else:
        status = "routed"

    portfolio_scope = (
        intent in {"portfolio_review", "portfolio_focus"}
        or (intent == "recent_activity" and (activity_all_projects or (continuation == "recent_activity" and all_project_reply)))
        or (
            intent in {"task_status", "deadline_review", "document_review", "workspace_gaps", "project_question"}
            and continuation == intent
            and all_project_reply
        )
        or (
            intent in {"task_status", "deadline_review", "document_review", "workspace_gaps", "today_focus"}
            and explicit_all_projects
        )
    ) and not requires_clarification
    return IntelligenceRouteDecision(
        query=raw_query,
        intent=intent,
        confidence=confidence,
        scope_type="portfolio" if portfolio_scope else (resolved.scope_type if resolved else None),
        scope_id=None if portfolio_scope else (resolved.scope_id if resolved else None),
        scope_label="All projects" if portfolio_scope else (resolved.label if resolved else None),
        status=status,
        requires_clarification=requires_clarification,
        clarification=clarification,
        candidates=candidates,
    )
