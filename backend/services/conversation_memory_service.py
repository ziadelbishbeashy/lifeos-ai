"""Conversational memory proposals for I16.1.

LifeOS may *propose* a structured memory from explicit user wording, but this
module never persists it. Persistence continues to use the existing I16 memory
endpoint and therefore always requires an explicit authenticated user action.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from services.ask_context_picker_service import AskContextOption


MAX_PROPOSAL_VALUE_CHARACTERS = 1200


@dataclass(frozen=True)
class ConversationMemorySuggestion:
    memory_type: str
    label: str
    value: str
    project_id: int | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.memory_type,
            "label": self.label,
            "value": self.value,
            "project_id": self.project_id,
            "reason": self.reason,
            "requires_confirmation": True,
        }


def _clean(value: str) -> str:
    return " ".join(str(value or "").split()).strip()[:MAX_PROPOSAL_VALUE_CHARACTERS]


def _strip_memory_command(text: str) -> str:
    value = text.strip()
    patterns = (
        r"^(?:please\s+)?remember\s+(?:that\s+)?",
        r"^(?:please\s+)?save\s+(?:this\s+)?(?:as\s+)?(?:a\s+)?(?:preference|memory)\s*[:,-]?\s*",
        r"^(?:please\s+)?keep\s+in\s+mind\s+(?:that\s+)?",
    )
    for pattern in patterns:
        updated = re.sub(pattern, "", value, flags=re.IGNORECASE).strip()
        if updated != value:
            return updated
    return value


def looks_like_memory_statement(text: str) -> bool:
    normalized = _clean(text).casefold()
    if not normalized or normalized.endswith("?"):
        return False
    markers = (
        "remember that", "remember this", "please remember", "keep in mind",
        "i prefer", "i'd prefer", "i would prefer", "my preference",
        "i want you to always", "from now on", "when you review", "when you answer", "always ",
        "do not ", "don't ", "my current focus", "i am focusing on", "i'm focusing on",
        "right now i am working on", "right now i'm working on", "my focus is",
    )
    return any(marker in normalized for marker in markers)


def propose_conversation_memory(
    *,
    text: str,
    selected_context: AskContextOption | None = None,
    force: bool = False,
) -> ConversationMemorySuggestion | None:
    cleaned = _clean(text)
    if not cleaned:
        return None
    if not force and not looks_like_memory_statement(cleaned):
        return None

    normalized = cleaned.casefold()
    focus_markers = (
        "my current focus", "i am focusing on", "i'm focusing on", "my focus is",
        "right now i am working on", "right now i'm working on", "currently focusing on",
    )
    memory_type = "current_focus" if any(marker in normalized for marker in focus_markers) else "preference"
    value = _clean(_strip_memory_command(cleaned))
    if not value or value.endswith("?"):
        return None

    project_id = None
    if selected_context is not None and selected_context.type == "project":
        # Scope only when the user explicitly chose a Project. Selecting a PDF
        # must not silently turn an answer-style preference into project memory.
        project_id = selected_context.id

    if memory_type == "current_focus":
        label = "Current focus"
        reason = "This sounds like an explicit current focus you may want LifeOS to reuse later."
    else:
        label = "Conversation preference"
        if selected_context is not None and selected_context.type == "project":
            label = f"{selected_context.label} preference"
        reason = "This sounds like a reusable preference. LifeOS will save it only if you confirm."

    return ConversationMemorySuggestion(memory_type, label, value, project_id, reason)
