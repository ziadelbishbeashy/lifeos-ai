"""Allow-listed tool registry for the LifeOS Intelligence Layer.

The model never receives database access. Intelligence workflows can only call
small, reviewed LifeOS tools registered here. The first Intelligence Core slice
is deliberately read-only; write/action tools will be introduced behind an
explicit confirmation boundary later.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping

from services.project_service import build_project_workspace
from services.workspace_context_service import (
    WorkspaceContextNotFoundError,
    build_project_documents_context,
    build_project_tasks_context,
    build_related_notes_context,
    require_owned_project,
)


class IntelligenceToolError(RuntimeError):
    """Base error for reviewed LifeOS intelligence tools."""


class IntelligenceToolNotFoundError(IntelligenceToolError, LookupError):
    """Raised when a workflow asks for a tool that is not allow-listed."""


class IntelligenceToolPermissionError(IntelligenceToolError, PermissionError):
    """Raised when a workflow tries to execute an unsafe tool mode."""


class IntelligenceToolInputError(IntelligenceToolError, ValueError):
    """Raised when an allow-listed tool receives invalid arguments."""


@dataclass(frozen=True)
class IntelligenceToolSpec:
    """Reviewed contract for one LifeOS capability exposed to orchestration."""

    name: str
    description: str
    risk: str
    scope: str
    input_fields: tuple[str, ...]
    handler: Callable[..., dict[str, Any]]

    @property
    def mutates_state(self) -> bool:
        return self.risk != "read_only"

    def public_contract(self) -> dict[str, Any]:
        """Return tool metadata without exposing Python implementation details."""

        return {
            "name": self.name,
            "description": self.description,
            "risk": self.risk,
            "scope": self.scope,
            "input_fields": list(self.input_fields),
            "mutates_state": self.mutates_state,
        }


@dataclass(frozen=True)
class IntelligenceToolResult:
    """Structured output from one allow-listed tool invocation."""

    tool_name: str
    scope: str
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IntelligenceToolRegistry:
    """Small explicit registry; unknown or mutating tools fail closed."""

    def __init__(self) -> None:
        self._tools: dict[str, IntelligenceToolSpec] = {}

    def register(self, spec: IntelligenceToolSpec) -> None:
        name = str(spec.name or "").strip()
        if not name:
            raise IntelligenceToolInputError("Intelligence tool name is required.")
        if name in self._tools:
            raise IntelligenceToolInputError(
                f'Intelligence tool "{name}" is already registered.'
            )
        self._tools[name] = spec

    def get(self, name: str) -> IntelligenceToolSpec:
        key = str(name or "").strip()
        spec = self._tools.get(key)
        if spec is None:
            raise IntelligenceToolNotFoundError(
                f'Intelligence tool "{key or "<empty>"}" is not available.'
            )
        return spec

    def list_contracts(self) -> list[dict[str, Any]]:
        return [
            self._tools[name].public_contract()
            for name in sorted(self._tools)
        ]

    def execute(
        self,
        name: str,
        *,
        owner_id: int,
        arguments: Mapping[str, Any] | None = None,
        allow_mutation: bool = False,
    ) -> IntelligenceToolResult:
        spec = self.get(name)
        if spec.mutates_state and not allow_mutation:
            raise IntelligenceToolPermissionError(
                f'Intelligence tool "{spec.name}" requires an explicit action boundary.'
            )

        args = dict(arguments or {})
        unexpected = sorted(set(args) - set(spec.input_fields))
        if unexpected:
            raise IntelligenceToolInputError(
                f'Unexpected input for {spec.name}: {", ".join(unexpected)}.'
            )
        missing = [field for field in spec.input_fields if field not in args]
        if missing:
            raise IntelligenceToolInputError(
                f'Missing input for {spec.name}: {", ".join(missing)}.'
            )

        try:
            data = spec.handler(owner_id=owner_id, **args)
        except WorkspaceContextNotFoundError:
            raise

        if not isinstance(data, dict):
            raise IntelligenceToolError(
                f'Intelligence tool "{spec.name}" returned an invalid result.'
            )

        return IntelligenceToolResult(
            tool_name=spec.name,
            scope=spec.scope,
            data=data,
        )


def _project_summary_tool(*, owner_id: int, project_id: int) -> dict[str, Any]:
    project = require_owned_project(owner_id=owner_id, project_id=project_id)
    workspace = build_project_workspace(project.id, owner_id)

    return {
        "project": {
            "id": project.id,
            "title": project.title,
            "description": project.description or "",
            "goal": project.goal or "",
            "status": project.status or "",
            "priority": project.priority or "",
            "current_phase": project.current_phase or "",
            "progress": int(project.progress or 0),
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "deadline": project.deadline.isoformat() if project.deadline else None,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        },
        "health": workspace.get("project_health"),
        "days_to_deadline": workspace.get("days_to_deadline"),
        "task_progress": int(workspace.get("task_progress") or 0),
        "total_tasks": int(workspace.get("total_tasks") or 0),
        "completed_tasks": int(workspace.get("completed_tasks") or 0),
        "overdue_tasks": len(workspace.get("overdue_tasks") or []),
        "blocked_tasks": int(workspace.get("blocked_tasks") or 0),
        "due_soon_tasks": len(workspace.get("due_soon_tasks") or []),
        "pending_document_suggestions": int(
            workspace.get("pending_document_suggestion_count") or 0
        ),
        "current_document_count": sum(
            1
            for document in (workspace.get("project_documents") or [])
            if bool(getattr(document, "is_current_version", False))
        ),
        "notes_count": int(workspace.get("notes_count") or 0),
    }


def _project_tasks_tool(*, owner_id: int, project_id: int) -> dict[str, Any]:
    require_owned_project(owner_id=owner_id, project_id=project_id)
    return build_project_tasks_context(owner_id=owner_id, project_id=project_id)


def _project_documents_tool(*, owner_id: int, project_id: int) -> dict[str, Any]:
    documents, counts = build_project_documents_context(
        owner_id=owner_id,
        project_id=project_id,
    )
    return {"documents": documents, "context_counts": counts}


def _project_notes_tool(*, owner_id: int, project_id: int) -> dict[str, Any]:
    require_owned_project(owner_id=owner_id, project_id=project_id)
    notes = build_related_notes_context(owner_id=owner_id, project_id=project_id)
    return {"notes": notes, "count": len(notes)}


def build_default_intelligence_tool_registry() -> IntelligenceToolRegistry:
    """Create the reviewed Intelligence Core V1 tool allow-list."""

    registry = IntelligenceToolRegistry()
    registry.register(
        IntelligenceToolSpec(
            name="project.get_summary",
            description="Read factual project state and deterministic project health.",
            risk="read_only",
            scope="project",
            input_fields=("project_id",),
            handler=_project_summary_tool,
        )
    )
    registry.register(
        IntelligenceToolSpec(
            name="project.get_tasks",
            description="Read bounded owned project tasks and status counts.",
            risk="read_only",
            scope="project",
            input_fields=("project_id",),
            handler=_project_tasks_tool,
        )
    )
    registry.register(
        IntelligenceToolSpec(
            name="project.get_documents",
            description=(
                "Read bounded current project-document intelligence with stale/current "
                "analysis status and provenance."
            ),
            risk="read_only",
            scope="project",
            input_fields=("project_id",),
            handler=_project_documents_tool,
        )
    )
    registry.register(
        IntelligenceToolSpec(
            name="project.get_recent_notes",
            description="Read bounded recent notes owned by the project owner.",
            risk="read_only",
            scope="project",
            input_fields=("project_id",),
            handler=_project_notes_tool,
        )
    )
    return registry


DEFAULT_INTELLIGENCE_TOOL_REGISTRY = build_default_intelligence_tool_registry()
