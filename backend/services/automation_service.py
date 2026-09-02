"""I17 automation definitions plus the I18 visual orchestration contract.

I17 automates verified intelligence work, not arbitrary code and not direct
workspace mutation. I18 validates and compiles richer visual metadata while I17 remains the runtime;
Project/Task/Note/Document writes still stay behind I9.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import true
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from database import db
from models import (
    Document,
    DocumentCollection,
    LearningModule,
    LifeOSAutomation,
    LifeOSAutomationRun,
    LifeOSIntelligenceEvent,
    Project,
)
from services.automation_flow_compiler_service import (
    AutomationFlowCompileError,
    compile_visual_flow,
)
from services.automation_intelligence_service import (
    build_event_context_review_output,
    build_risk_escalation_output,
    build_today_briefing_output,
    build_unhandled_followup_output,
    build_weekly_review_output,
)


TRIGGER_TYPES = {
    "schedule_daily": {
        "label": "Every day",
        "description": "Run once each day at a selected local time.",
        "fields": ["hour", "minute"],
    },
    "schedule_weekly": {
        "label": "Every week",
        "description": "Run once each week on a selected weekday and time.",
        "fields": ["weekday", "hour", "minute"],
    },
    "event": {
        "label": "When something changes",
        "description": "Run when an allow-listed I14 event becomes relevant.",
        "fields": ["event_type"],
    },
    "manual": {
        "label": "Manual run only",
        "description": "Run only when the owner explicitly presses Run now.",
        "fields": [],
    },
}

EVENT_TYPES = {
    "task.overdue",
    "task.blocked",
    "deadline.approaching",
    "project.overdue",
    "project.deadline_approaching",
    "document.intelligence_stale",
    "document.version_changed",
}

ACTION_TYPES = {
    "today_briefing": {
        "label": "Morning intelligence briefing",
        "description": "Combine priorities, deadlines, document attention, study state, and recent changes into Today's verified briefing.",
        "scope": "workspace",
    },
    "portfolio_review": {
        "label": "Weekly intelligence review",
        "description": "Review all projects plus this week's meaningful activity and rank what deserves attention next.",
        "scope": "workspace",
    },
    "project_review": {
        "label": "Review one project",
        "description": "Run the constrained I8 project review agent for one owned project.",
        "scope": "project",
    },
    "risk_escalation": {
        "label": "Detect compound project risk",
        "description": "Escalate only when several trusted signals combine into a broader project risk; do not repeat basic due-task reminders.",
        "scope": "workspace",
    },
    "unhandled_followup": {
        "label": "Find unhandled document follow-ups",
        "description": "Find current document risks/actions that still have no confirmed task or note provenance.",
        "scope": "workspace",
    },
    "attention_notice": {
        "label": "Review a triggering event in context",
        "description": "Enrich a selected I14 event with relevant project priorities before notifying you.",
        "scope": "event",
    },
    "custom_ask": {
        "label": "Ask LifeOS a custom question",
        "description": "Run one user-written read-only Ask LifeOS instruction inside the flow's verified context.",
        "scope": "selected_context",
        "visual_only": True,
    },
}

MAX_AUTOMATIONS_PER_USER = 50
MAX_RUN_HISTORY = 100

VISUAL_FLOW_VERSION = 1
VISUAL_FLOW_PHASE = "I18.6"
VISUAL_CATEGORY_ORDER = ("trigger", "context", "intelligence", "condition", "output", "proposal")
VISUAL_REQUIRED_CATEGORIES = ("trigger", "intelligence", "output")
VISUAL_DEFAULT_POSITIONS = {
    "trigger": {"x": 80.0, "y": 150.0},
    "context": {"x": 340.0, "y": 150.0},
    "intelligence": {"x": 600.0, "y": 150.0},
    "condition": {"x": 860.0, "y": 150.0},
    "output": {"x": 1120.0, "y": 150.0},
    "proposal": {"x": 1380.0, "y": 150.0},
}
VISUAL_NODE_ID_MAX = 64
VISUAL_MAX_NODES = 16
VISUAL_MAX_EDGES = 15
VISUAL_MAX_PER_CATEGORY = {
    "trigger": 1,
    "context": 3,
    "intelligence": 6,
    "condition": 3,
    "output": 1,
    "proposal": 1,
}
VISUAL_CONNECTION_RULES = {
    ("trigger", "context"),
    ("trigger", "intelligence"),
    ("context", "context"),
    ("context", "intelligence"),
    ("intelligence", "intelligence"),
    ("intelligence", "condition"),
    ("condition", "condition"),
    ("condition", "output"),
    ("condition", "proposal"),
    ("intelligence", "output"),
    ("intelligence", "proposal"),
    ("output", "proposal"),
}

# I18 keeps the I17 runtime authoritative while allowing the visual graph to
# express a richer, compiler-validated linear orchestration plan. The compiler
# emits only approved LifeOS capability keys, and the I17 executor interprets
# those plans through approved service bindings.
VISUAL_NODE_REGISTRY: dict[str, dict[str, Any]] = {
    "trigger.schedule_daily": {
        "category": "trigger",
        "label": "Schedule · Daily",
        "description": "Run once each day at a selected local time.",
        "icon": "clock",
        "availability": "i18_1",
        "binding": {"trigger_type": "schedule_daily"},
    },
    "trigger.schedule_weekly": {
        "category": "trigger",
        "label": "Schedule · Weekly",
        "description": "Run once each week on a selected weekday and time.",
        "icon": "calendar",
        "availability": "i18_1",
        "binding": {"trigger_type": "schedule_weekly"},
    },
    "trigger.task_overdue": {
        "category": "trigger",
        "label": "Task Overdue",
        "description": "Start from the approved I14 task.overdue event.",
        "icon": "alert",
        "availability": "i18_1",
        "binding": {"trigger_type": "event", "event_type": "task.overdue"},
    },
    "trigger.deadline_approaching": {
        "category": "trigger",
        "label": "Deadline Approaching",
        "description": "Start from the approved I14 deadline.approaching event.",
        "icon": "deadline",
        "availability": "i18_1",
        "binding": {"trigger_type": "event", "event_type": "deadline.approaching"},
    },
    "trigger.document_stale": {
        "category": "trigger",
        "label": "Document Stale",
        "description": "Start when document intelligence is marked stale.",
        "icon": "document",
        "availability": "i18_1",
        "binding": {"trigger_type": "event", "event_type": "document.intelligence_stale"},
    },
    "trigger.document_version_changed": {
        "category": "trigger",
        "label": "Document Version Changed",
        "description": "Start from the approved document.version_changed event.",
        "icon": "version",
        "availability": "i18_1",
        "binding": {"trigger_type": "event", "event_type": "document.version_changed"},
    },
    "trigger.task_blocked": {
        "category": "trigger",
        "label": "Task Blocked",
        "description": "Start from the approved I14 task.blocked event.",
        "icon": "blocked",
        "availability": "i18_1",
        "binding": {"trigger_type": "event", "event_type": "task.blocked"},
    },
    "trigger.project_overdue": {
        "category": "trigger",
        "label": "Project Overdue",
        "description": "Start from the approved I14 project.overdue event.",
        "icon": "project",
        "availability": "i18_1",
        "binding": {"trigger_type": "event", "event_type": "project.overdue"},
    },
    "trigger.project_deadline_approaching": {
        "category": "trigger",
        "label": "Project Deadline Approaching",
        "description": "Start from the approved project.deadline_approaching event.",
        "icon": "project",
        "availability": "i18_1",
        "binding": {"trigger_type": "event", "event_type": "project.deadline_approaching"},
    },
    "trigger.manual_run": {
        "category": "trigger",
        "label": "Manual Run",
        "description": "Run only from an explicit owner action. This trigger is never picked up by the background worker.",
        "icon": "play",
        "availability": "i18_6",
        "binding": {"trigger_type": "manual"},
    },
    "context.all_lifeos": {
        "category": "context",
        "label": "All LifeOS",
        "description": "Compile an explicit whole-workspace context boundary.",
        "icon": "workspace",
        "availability": "i18_2",
        "binding": {},
    },
    "context.project": {
        "category": "context",
        "label": "Project Context",
        "description": "Compile an explicit owned-project context boundary or inherit project scope from the triggering I14 event.",
        "icon": "project",
        "availability": "i18_2",
        "binding": {},
    },
    "context.document": {
        "category": "context",
        "label": "Document Context",
        "description": "Compile a selected document or triggering document into the authoritative Document Brain/RAG context boundary.",
        "icon": "document",
        "availability": "i18_2",
        "binding": {},
    },
    "context.module": {
        "category": "context",
        "label": "Module Context",
        "description": "Compile an explicit owned learning-module context boundary.",
        "icon": "module",
        "availability": "i18_2",
        "binding": {},
    },
    "context.collection": {
        "category": "context",
        "label": "Collection Context",
        "description": "Compile an owned collection context that will reuse the existing collection RAG path.",
        "icon": "collection",
        "availability": "i18_2",
        "binding": {},
    },
    "context.recent_activity": {
        "category": "context",
        "label": "Recent Activity",
        "description": "Compile verified I10 recent activity into the flow context.",
        "icon": "activity",
        "availability": "i18_2",
        "binding": {},
    },
    "intelligence.today_briefing": {
        "category": "intelligence",
        "label": "Build Today Briefing",
        "description": ACTION_TYPES["today_briefing"]["description"],
        "icon": "spark",
        "availability": "i18_1",
        "binding": {"action_type": "today_briefing"},
    },
    "intelligence.portfolio_review": {
        "category": "intelligence",
        "label": "Review Workspace",
        "description": ACTION_TYPES["portfolio_review"]["description"],
        "icon": "review",
        "availability": "i18_1",
        "binding": {"action_type": "portfolio_review"},
    },
    "intelligence.project_review": {
        "category": "intelligence",
        "label": "Review Project",
        "description": ACTION_TYPES["project_review"]["description"],
        "icon": "project",
        "availability": "i18_1",
        "binding": {"action_type": "project_review"},
    },
    "intelligence.detect_risks": {
        "category": "intelligence",
        "label": "Detect Risks",
        "description": ACTION_TYPES["risk_escalation"]["description"],
        "icon": "risk",
        "availability": "i18_1",
        "binding": {"action_type": "risk_escalation"},
    },
    "intelligence.find_unhandled_findings": {
        "category": "intelligence",
        "label": "Find Unhandled Findings",
        "description": ACTION_TYPES["unhandled_followup"]["description"],
        "icon": "find",
        "availability": "i18_1",
        "binding": {"action_type": "unhandled_followup"},
    },
    "intelligence.event_context_review": {
        "category": "intelligence",
        "label": "Review Triggering Event",
        "description": ACTION_TYPES["attention_notice"]["description"],
        "icon": "event",
        "availability": "i18_1",
        "binding": {"action_type": "attention_notice"},
    },
    "intelligence.review_document": {
        "category": "intelligence",
        "label": "Review Document",
        "description": "Compile document review through the existing Document Brain/RAG boundary; no parallel RAG pipeline is introduced.",
        "icon": "document",
        "availability": "i18_2",
        "binding": {},
    },
    "intelligence.rank_priorities": {
        "category": "intelligence",
        "label": "Rank Priorities",
        "description": "Compile priority ranking to the existing LifeOS project/portfolio intelligence boundary.",
        "icon": "rank",
        "availability": "i18_2",
        "binding": {},
    },
    "intelligence.what_changed": {
        "category": "intelligence",
        "label": "What Changed",
        "description": "Compile a What Changed step to verified I10 recent activity intelligence.",
        "icon": "activity",
        "availability": "i18_2",
        "binding": {},
    },
    "intelligence.ask_lifeos": {
        "category": "intelligence",
        "label": "Ask LifeOS",
        "description": "Run one custom read-only Ask LifeOS instruction inside the selected verified context. The instruction cannot execute tools or mutate the workspace.",
        "icon": "spark",
        "availability": "i18_6",
        "binding": {"action_type": "custom_ask"},
    },
    "condition.attention_needed": {
        "category": "condition",
        "label": "Only If Attention Is Needed",
        "description": "Continue only when the previous verified result reaches the selected attention level. Otherwise the flow ends quietly.",
        "icon": "filter",
        "availability": "i18_6",
        "binding": {},
    },
    "condition.results_found": {
        "category": "condition",
        "label": "Only If Results Were Found",
        "description": "Continue only when the previous verified step produced findings, priorities, items, or a non-empty answer.",
        "icon": "filter",
        "availability": "i18_6",
        "binding": {},
    },
    "output.notify_me": {
        "category": "output",
        "label": "Notify Me",
        "description": "Deliver the verified result through the existing I14 → I15 notification path.",
        "icon": "bell",
        "availability": "i18_1",
        "binding": {"delivery": "in_app_notification"},
    },
    "output.save_review_result": {
        "category": "output",
        "label": "Save Review Result",
        "description": "Compile an explicit save-to-automation-run result step. This does not create or edit workspace resources.",
        "icon": "save",
        "availability": "i18_2",
        "binding": {},
    },
    "output.suggest_action": {
        "category": "output",
        "label": "Suggest Action",
        "description": "Compile a suggestion output. Any workspace mutation still requires a separate I9-confirmed proposal.",
        "icon": "suggest",
        "availability": "i18_2",
        "binding": {},
    },
    "proposal.create_task": {
        "category": "proposal",
        "label": "Propose Create Task",
        "description": "Compile a create-task proposal only. It never writes directly; I9 confirmation remains mandatory.",
        "icon": "task",
        "availability": "i18_2",
        "binding": {},
        "confirmation_boundary": "I9",
    },
    "proposal.save_note": {
        "category": "proposal",
        "label": "Propose Save Note",
        "description": "Compile a save-note proposal only. It never writes directly; I9 confirmation remains mandatory.",
        "icon": "note",
        "availability": "i18_2",
        "binding": {},
        "confirmation_boundary": "I9",
    },
    "proposal.refresh_analysis": {
        "category": "proposal",
        "label": "Propose Refresh Analysis",
        "description": "Compile a refresh-analysis proposal only. Execution must use approved services and retain the I9 confirmation boundary.",
        "icon": "refresh",
        "availability": "i18_2",
        "binding": {},
        "confirmation_boundary": "I9",
    },
}


_VISUAL_COMPILER_BINDINGS: dict[str, dict[str, Any]] = {
    "trigger.schedule_daily": {"capability": "schedule.daily", "service_boundary": "I17.scheduler", "input_contract": "validated_schedule", "output_contract": "trigger_signal"},
    "trigger.schedule_weekly": {"capability": "schedule.weekly", "service_boundary": "I17.scheduler", "input_contract": "validated_schedule", "output_contract": "trigger_signal"},
    "trigger.task_overdue": {"capability": "event.task_overdue", "service_boundary": "I14.event_engine", "input_contract": "verified_i14_event", "output_contract": "trigger_signal"},
    "trigger.deadline_approaching": {"capability": "event.deadline_approaching", "service_boundary": "I14.event_engine", "input_contract": "verified_i14_event", "output_contract": "trigger_signal"},
    "trigger.document_stale": {"capability": "event.document_stale", "service_boundary": "I14.event_engine", "input_contract": "verified_i14_event", "output_contract": "trigger_signal"},
    "trigger.document_version_changed": {"capability": "event.document_version_changed", "service_boundary": "I14.event_engine", "input_contract": "verified_i14_event", "output_contract": "trigger_signal"},
    "trigger.task_blocked": {"capability": "event.task_blocked", "service_boundary": "I14.event_engine", "input_contract": "verified_i14_event", "output_contract": "trigger_signal"},
    "trigger.project_overdue": {"capability": "event.project_overdue", "service_boundary": "I14.event_engine", "input_contract": "verified_i14_event", "output_contract": "trigger_signal"},
    "trigger.project_deadline_approaching": {"capability": "event.project_deadline_approaching", "service_boundary": "I14.event_engine", "input_contract": "verified_i14_event", "output_contract": "trigger_signal"},
    "trigger.manual_run": {"capability": "manual.run", "service_boundary": "I17.executor", "input_contract": "explicit_user_run", "output_contract": "trigger_signal"},
    "context.all_lifeos": {"capability": "context.all_lifeos", "service_boundary": "I2.context_engine", "output_contract": "owned_workspace_context"},
    "context.project": {"capability": "context.project", "service_boundary": "I2.context_engine", "output_contract": "owned_project_context"},
    "context.document": {"capability": "context.document", "service_boundary": "DocumentBrain.authoritative_rag", "output_contract": "owned_document_context"},
    "context.module": {"capability": "context.module", "service_boundary": "Modules.context", "output_contract": "owned_module_context"},
    "context.collection": {"capability": "context.collection", "service_boundary": "DocumentBrain.collection_rag", "output_contract": "owned_collection_context"},
    "context.recent_activity": {"capability": "context.recent_activity", "service_boundary": "I10.recent_activity", "output_contract": "verified_activity_context"},
    "intelligence.today_briefing": {"capability": "intelligence.today_briefing", "service_boundary": "I12.today_intelligence", "output_contract": "verified_briefing"},
    "intelligence.portfolio_review": {"capability": "intelligence.portfolio_review", "service_boundary": "I8.portfolio_review", "output_contract": "verified_review"},
    "intelligence.project_review": {"capability": "intelligence.project_review", "service_boundary": "I8.project_review", "output_contract": "verified_review"},
    "intelligence.detect_risks": {"capability": "intelligence.detect_risks", "service_boundary": "I17.risk_intelligence", "output_contract": "verified_risks"},
    "intelligence.find_unhandled_findings": {"capability": "intelligence.find_unhandled_findings", "service_boundary": "I17.document_followup", "output_contract": "verified_findings"},
    "intelligence.event_context_review": {"capability": "intelligence.event_context_review", "service_boundary": "I14.event_context", "output_contract": "verified_review"},
    "intelligence.review_document": {"capability": "intelligence.review_document", "service_boundary": "DocumentBrain.authoritative_rag", "input_contract": "owned_document_context", "output_contract": "grounded_document_review"},
    "intelligence.rank_priorities": {"capability": "intelligence.rank_priorities", "service_boundary": "I8.portfolio_review", "output_contract": "verified_ranked_priorities"},
    "intelligence.what_changed": {"capability": "intelligence.what_changed", "service_boundary": "I10.recent_activity", "output_contract": "verified_change_summary"},
    "intelligence.ask_lifeos": {"capability": "intelligence.ask_lifeos", "service_boundary": "I3_I4_I5.ask_lifeos", "input_contract": "verified_scope_plus_user_instruction", "output_contract": "verified_custom_answer"},
    "condition.attention_needed": {"capability": "condition.attention_needed", "service_boundary": "I18.safe_gate", "input_contract": "verified_result", "output_contract": "continue_or_stop", "read_only": True},
    "condition.results_found": {"capability": "condition.results_found", "service_boundary": "I18.safe_gate", "input_contract": "verified_result", "output_contract": "continue_or_stop", "read_only": True},
    "output.notify_me": {"capability": "output.notify_me", "service_boundary": "I14_I15.notification", "input_contract": "verified_result", "output_contract": "notification_metadata"},
    "output.save_review_result": {"capability": "output.save_review_result", "service_boundary": "I17.automation_run_audit", "input_contract": "verified_result", "output_contract": "automation_run_output"},
    "output.suggest_action": {"capability": "output.suggest_action", "service_boundary": "I9.action_proposal", "input_contract": "verified_result", "output_contract": "unconfirmed_action_suggestion"},
    "proposal.create_task": {"capability": "proposal.create_task", "service_boundary": "I9.confirmed_actions", "input_contract": "verified_suggestion", "output_contract": "confirmation_request", "confirmation_boundary": "I9"},
    "proposal.save_note": {"capability": "proposal.save_note", "service_boundary": "I9.confirmed_actions", "input_contract": "verified_suggestion", "output_contract": "confirmation_request", "confirmation_boundary": "I9"},
    "proposal.refresh_analysis": {"capability": "proposal.refresh_analysis", "service_boundary": "I9.confirmed_actions", "input_contract": "verified_suggestion", "output_contract": "confirmation_request", "confirmation_boundary": "I9"},
}

for _node_type, _compiler in _VISUAL_COMPILER_BINDINGS.items():
    VISUAL_NODE_REGISTRY[_node_type]["compiler"] = dict(_compiler)


class AutomationValidationError(ValueError):
    pass


class AutomationNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class AutomationPreviewResult:
    automation: LifeOSAutomation
    run: LifeOSAutomationRun
    output: dict[str, Any]

    @property
    def status(self) -> str:
        """Stable lifecycle label for preview responses.

        The persisted run still records its own execution status (for example
        ``succeeded`` or ``failed``).  This property describes the operation
        requested by the caller and keeps preview consumers from inferring that
        lifecycle label from the run record.
        """
        return "preview"

    def to_dict(self) -> dict[str, Any]:
        return {
            "automation": automation_to_dict(self.automation),
            "run": automation_run_to_dict(self.run),
            "output": self.output,
            "verified_from_state": True,
            "workspace_mutation": False,
            "execution_mode": "preview",
        }


def _finite_position(value: Any, *, fallback: dict[str, float]) -> dict[str, float]:
    raw = value if isinstance(value, dict) else {}
    result: dict[str, float] = {}
    for key in ("x", "y"):
        candidate = raw.get(key, fallback[key])
        try:
            parsed = float(candidate)
        except (TypeError, ValueError) as error:
            raise AutomationValidationError("Visual flow node positions must be numeric.") from error
        if parsed != parsed or parsed in (float("inf"), float("-inf")) or abs(parsed) > 5000:
            raise AutomationValidationError("Visual flow node position is outside the supported canvas.")
        result[key] = round(parsed, 2)
    return result


def _visual_node_type_for_trigger(trigger_type: str, trigger_config: dict[str, Any] | None = None) -> str:
    config = trigger_config if isinstance(trigger_config, dict) else {}
    if trigger_type == "schedule_daily":
        return "trigger.schedule_daily"
    if trigger_type == "schedule_weekly":
        return "trigger.schedule_weekly"
    if trigger_type == "manual":
        return "trigger.manual_run"
    if trigger_type == "event":
        event_type = str(config.get("event_type") or "").strip()
        for node_type, definition in VISUAL_NODE_REGISTRY.items():
            binding = definition.get("binding") if isinstance(definition, dict) else None
            if (
                definition.get("category") == "trigger"
                and definition.get("availability") == "i18_1"
                and isinstance(binding, dict)
                and binding.get("trigger_type") == "event"
                and binding.get("event_type") == event_type
            ):
                return node_type
        # Existing malformed/stale rows should remain inspectable; validation of
        # user writes still happens through validate_trigger before this helper.
        return "trigger.task_overdue"
    raise AutomationValidationError("Unsupported automation trigger for the visual flow.")


def _visual_node_type_for_action(action_type: str) -> str:
    for node_type, definition in VISUAL_NODE_REGISTRY.items():
        binding = definition.get("binding") if isinstance(definition, dict) else None
        if (
            definition.get("category") == "intelligence"
            and definition.get("availability") in {"i18_1", "i18_6"}
            and isinstance(binding, dict)
            and binding.get("action_type") == action_type
        ):
            return node_type
    raise AutomationValidationError("Unsupported automation action for the visual flow.")


def _visual_semantic_type(node_type: str, *, trigger_type: str, action_type: str) -> str:
    category = str(VISUAL_NODE_REGISTRY[node_type].get("category"))
    if category == "trigger":
        return trigger_type
    if category == "intelligence":
        return action_type
    return "in_app_notification"


def default_visual_graph(
    *,
    trigger_type: str,
    action_type: str,
    trigger_config: dict[str, Any] | None = None,
    action_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trigger_node_type = _visual_node_type_for_trigger(trigger_type, trigger_config)
    intelligence_node_type = _visual_node_type_for_action(action_type)
    nodes = [
        {
            "id": "trigger-1",
            "type": trigger_node_type,
            "category": "trigger",
            "position": dict(VISUAL_DEFAULT_POSITIONS["trigger"]),
            "config": dict(trigger_config or {}),
            "semantic_type": trigger_type,
        },
        {
            "id": "intelligence-1",
            "type": intelligence_node_type,
            "category": "intelligence",
            "position": dict(VISUAL_DEFAULT_POSITIONS["intelligence"]),
            "config": dict(action_config or {}),
            "semantic_type": action_type,
        },
        {
            "id": "output-1",
            "type": "output.notify_me",
            "category": "output",
            "position": dict(VISUAL_DEFAULT_POSITIONS["output"]),
            "config": {},
            "semantic_type": "in_app_notification",
        },
    ]
    return {
        "version": VISUAL_FLOW_VERSION,
        "phase": VISUAL_FLOW_PHASE,
        "nodes": nodes,
        "edges": [
            {"id": "edge-trigger-intelligence", "source": "trigger-1", "target": "intelligence-1"},
            {"id": "edge-intelligence-output", "source": "intelligence-1", "target": "output-1"},
        ],
        "execution_binding": {
            "source": "I17_allowlisted_trigger_and_action",
            "graph_is_execution_source": False,
            "compiler_is_execution_source": True,
            "trigger_node_id": "trigger-1",
            "action_node_id": "intelligence-1",
            "i17_anchor_node_id": "intelligence-1",
            "output_node_id": "output-1",
            "rich_graph_execution_phase": "I18.6",
        },
        "safety": {
            "workspace_mutation": False,
            "delivery": "in_app",
            "future_workspace_actions_require": "I9_confirmation",
            "arbitrary_code": False,
            "arbitrary_sql": False,
            "arbitrary_urls": False,
            "direct_model_access": False,
        },
    }


def _legacy_visual_graph(
    raw: dict[str, Any],
    *,
    trigger_type: str,
    action_type: str,
    trigger_config: dict[str, Any],
    action_config: dict[str, Any],
) -> dict[str, Any] | None:
    """Upgrade the pre-registry three-node I18 scaffold without changing I17 semantics."""

    raw_nodes = raw.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        return None
    legacy_categories: dict[str, dict[str, Any]] = {}
    for node in raw_nodes:
        if not isinstance(node, dict):
            return None
        kind = str(node.get("kind") or "").strip()
        node_id = str(node.get("id") or "").strip()
        category = "output" if kind == "delivery" or node_id == "delivery" else kind
        if category not in VISUAL_REQUIRED_CATEGORIES or category in legacy_categories:
            return None
        legacy_categories[category] = node
    if set(legacy_categories) != set(VISUAL_REQUIRED_CATEGORIES):
        return None

    raw_edges = raw.get("edges")
    if not isinstance(raw_edges, list) or len(raw_edges) != 2:
        raise AutomationValidationError("Legacy visual flow connections are incomplete.")
    legacy_ids = {category: _validate_visual_node_id(node.get("id")) for category, node in legacy_categories.items()}
    actual_pairs = {
        (str(edge.get("source") or "").strip(), str(edge.get("target") or "").strip())
        for edge in raw_edges
        if isinstance(edge, dict)
    }
    expected_pairs = {
        (legacy_ids["trigger"], legacy_ids["intelligence"]),
        (legacy_ids["intelligence"], legacy_ids["output"]),
    }
    if actual_pairs != expected_pairs:
        raise AutomationValidationError("Legacy visual flow connections must form Trigger → Intelligence → Output.")

    canonical = default_visual_graph(
        trigger_type=trigger_type,
        trigger_config=trigger_config,
        action_type=action_type,
        action_config=action_config,
    )
    ids_by_category: dict[str, str] = {}
    for canonical_node in canonical["nodes"]:
        category = canonical_node["category"]
        legacy_node = legacy_categories[category]
        legacy_id = _validate_visual_node_id(legacy_node.get("id") or canonical_node["id"])
        canonical_node["id"] = legacy_id
        canonical_node["position"] = _finite_position(
            legacy_node.get("position"),
            fallback=VISUAL_DEFAULT_POSITIONS[category],
        )
        ids_by_category[category] = legacy_id
    canonical["edges"] = [
        {"id": "edge-trigger-intelligence", "source": ids_by_category["trigger"], "target": ids_by_category["intelligence"]},
        {"id": "edge-intelligence-output", "source": ids_by_category["intelligence"], "target": ids_by_category["output"]},
    ]
    canonical["execution_binding"].update({
        "trigger_node_id": ids_by_category["trigger"],
        "action_node_id": ids_by_category["intelligence"],
        "i17_anchor_node_id": ids_by_category["intelligence"],
        "output_node_id": ids_by_category["output"],
    })
    return canonical


def _validate_visual_node_id(value: Any) -> str:
    node_id = str(value or "").strip()
    if not node_id or len(node_id) > VISUAL_NODE_ID_MAX:
        raise AutomationValidationError("Visual flow node id is invalid.")
    if any(not (character.isalnum() or character in "-_") for character in node_id):
        raise AutomationValidationError("Visual flow node ids may contain only letters, numbers, dashes, and underscores.")
    return node_id


def _graph_has_cycle(node_ids: set[str], edges: list[dict[str, str]]) -> bool:
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    indegree: dict[str, int] = {node_id: 0 for node_id in node_ids}
    for edge in edges:
        outgoing[edge["source"]].append(edge["target"])
        indegree[edge["target"]] += 1
    queue = [node_id for node_id, degree in indegree.items() if degree == 0]
    visited = 0
    while queue:
        node_id = queue.pop()
        visited += 1
        for target in outgoing[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    return visited != len(node_ids)


def _linear_visual_order(node_ids: set[str], edges: list[dict[str, str]]) -> list[str]:
    indegree = {node_id: 0 for node_id in node_ids}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        indegree[edge["target"]] += 1
        outgoing[edge["source"]].append(edge["target"])
    if any(degree > 1 for degree in indegree.values()) or any(len(targets) > 1 for targets in outgoing.values()):
        raise AutomationValidationError("The visual flow builder supports one linear flow; branching and merging are not enabled yet.")
    roots = [node_id for node_id, degree in indegree.items() if degree == 0]
    if len(roots) != 1:
        raise AutomationValidationError("Visual flows require exactly one root Trigger.")
    order: list[str] = []
    current: str | None = roots[0]
    seen: set[str] = set()
    while current is not None:
        if current in seen:
            raise AutomationValidationError("Visual flow cycles are not supported in the visual flow builder.")
        seen.add(current)
        order.append(current)
        targets = outgoing[current]
        current = targets[0] if targets else None
    if len(order) != len(node_ids):
        raise AutomationValidationError("Every node must belong to one connected visual flow.")
    return order


def _owned_resource_id(*, owner_id: int | None, model: Any, value: Any, label: str) -> int:
    if owner_id is None:
        raise AutomationValidationError(f"{label} ownership can only be validated for an authenticated owner.")
    resource_id = _int_between(value, 1, 2_147_483_647, label)
    if model.query.filter_by(id=resource_id, user_id=owner_id).first() is None:
        raise AutomationValidationError(f"Selected {label.lower()} was not found.")
    return resource_id


def _canonical_context_config(
    *,
    node_type: str,
    raw: Any,
    owner_id: int | None,
    trigger_type: str,
    trigger_config: dict[str, Any],
) -> dict[str, Any]:
    config = raw if isinstance(raw, dict) else {}
    if node_type == "context.all_lifeos":
        return {}
    if node_type == "context.recent_activity":
        window = str(config.get("window") or "week").strip().casefold()
        if window not in {"today", "week"}:
            raise AutomationValidationError("Recent Activity context window must be Today or Week.")
        return {"window": window}

    mode = str(config.get("scope_mode") or "selected").strip().casefold()
    if mode not in {"selected", "trigger"}:
        raise AutomationValidationError("Context scope must use a selected owned resource or the verified trigger context.")

    if node_type == "context.project":
        if mode == "trigger":
            if trigger_type != "event":
                raise AutomationValidationError("Project Context can inherit from the trigger only for an I14 event flow.")
            return {"scope_mode": "trigger"}
        return {
            "scope_mode": "selected",
            "project_id": _owned_resource_id(owner_id=owner_id, model=Project, value=config.get("project_id"), label="Project"),
        }

    if node_type == "context.document":
        if mode == "trigger":
            event_type = str(trigger_config.get("event_type") or "")
            if trigger_type != "event" or event_type not in {"document.intelligence_stale", "document.version_changed"}:
                raise AutomationValidationError("Document Context can inherit from the trigger only for a document I14 event.")
            return {"scope_mode": "trigger"}
        return {
            "scope_mode": "selected",
            "document_id": _owned_resource_id(owner_id=owner_id, model=Document, value=config.get("document_id"), label="Document"),
        }

    if node_type == "context.module":
        if mode == "trigger":
            raise AutomationValidationError("Module Context requires a selected owned module in the visual flow builder.")
        return {
            "scope_mode": "selected",
            "module_id": _owned_resource_id(owner_id=owner_id, model=LearningModule, value=config.get("module_id"), label="Module"),
        }

    if node_type == "context.collection":
        if mode == "trigger":
            raise AutomationValidationError("Collection Context requires a selected owned collection in the visual flow builder.")
        return {
            "scope_mode": "selected",
            "collection_id": _owned_resource_id(owner_id=owner_id, model=DocumentCollection, value=config.get("collection_id"), label="Collection"),
        }
    raise AutomationValidationError("Unsupported visual context node.")


def _canonical_intelligence_config(
    *,
    node_type: str,
    raw: Any,
    owner_id: int | None,
    is_i17_anchor: bool,
    authoritative_action_type: str,
    authoritative_action_config: dict[str, Any],
) -> dict[str, Any]:
    definition = VISUAL_NODE_REGISTRY[node_type]
    binding = definition.get("binding") if isinstance(definition, dict) else {}
    bound_action = str((binding or {}).get("action_type") or "")
    if is_i17_anchor:
        if bound_action != authoritative_action_type:
            raise AutomationValidationError("The compiled flow's I17 storage anchor does not match the authoritative action.")
        return dict(authoritative_action_config)
    if bound_action == "project_review":
        if owner_id is None:
            raise AutomationValidationError("Project Review ownership can only be validated for an authenticated owner.")
        _kind, config = validate_action(owner_id=owner_id, action_type="project_review", raw=raw)
        return config
    if node_type == "intelligence.ask_lifeos":
        config = raw if isinstance(raw, dict) else {}
        instruction = " ".join(str(config.get("instruction") or "").split())
        if len(instruction) < 3:
            raise AutomationValidationError("Ask LifeOS needs a short instruction or question.")
        if len(instruction) > 600:
            raise AutomationValidationError("Ask LifeOS instructions can contain at most 600 characters.")
        return {"instruction": instruction}
    return {}


def _canonical_condition_config(*, node_type: str, raw: Any) -> dict[str, Any]:
    config = raw if isinstance(raw, dict) else {}
    if node_type == "condition.attention_needed":
        minimum = str(config.get("minimum_attention") or "medium").strip().casefold()
        if minimum not in {"medium", "high", "critical"}:
            raise AutomationValidationError("Attention gate must use Medium, High, or Critical.")
        return {"minimum_attention": minimum}
    if node_type == "condition.results_found":
        return {}
    raise AutomationValidationError("Unsupported visual condition node.")


def validate_visual_graph(
    raw: Any,
    *,
    trigger_type: str,
    action_type: str,
    trigger_config: dict[str, Any] | None = None,
    action_config: dict[str, Any] | None = None,
    owner_id: int | None = None,
) -> dict[str, Any]:
    """Validate and canonicalize visual orchestration metadata.

    The persisted graph is richer than I18.1 but remains declarative only. It is
    constrained to one connected linear path and allow-listed LifeOS node types.
    The backend compiler may translate it into an execution *plan*, but I17 stays
    the active runtime. Complex plans compile to approved capabilities and execute
    only through the I17 runtime adapter.
    """

    authoritative_trigger_config = dict(trigger_config or {})
    authoritative_action_config = dict(action_config or {})
    if raw in (None, {}, ""):
        return default_visual_graph(
            trigger_type=trigger_type,
            trigger_config=authoritative_trigger_config,
            action_type=action_type,
            action_config=authoritative_action_config,
        )
    if not isinstance(raw, dict):
        raise AutomationValidationError("Visual flow must be an object.")
    try:
        version = int(raw.get("version", VISUAL_FLOW_VERSION))
    except (TypeError, ValueError) as error:
        raise AutomationValidationError("Unsupported visual flow version.") from error
    if version != VISUAL_FLOW_VERSION:
        raise AutomationValidationError("Unsupported visual flow version.")

    legacy = _legacy_visual_graph(
        raw,
        trigger_type=trigger_type,
        action_type=action_type,
        trigger_config=authoritative_trigger_config,
        action_config=authoritative_action_config,
    )
    if legacy is not None:
        return legacy

    raw_nodes = raw.get("nodes")
    if not isinstance(raw_nodes, list) or len(raw_nodes) < 3 or len(raw_nodes) > VISUAL_MAX_NODES:
        raise AutomationValidationError(f"Visual flows must contain between 3 and {VISUAL_MAX_NODES} nodes.")

    nodes_by_id: dict[str, dict[str, Any]] = {}
    category_counts: dict[str, int] = {category: 0 for category in VISUAL_CATEGORY_ORDER}
    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict):
            raise AutomationValidationError("Invalid visual flow node.")
        node_id = _validate_visual_node_id(raw_node.get("id"))
        if node_id in nodes_by_id:
            raise AutomationValidationError("Visual flow node ids must be unique.")
        node_type = str(raw_node.get("type") or "").strip()
        definition = VISUAL_NODE_REGISTRY.get(node_type)
        if definition is None:
            raise AutomationValidationError("Visual flow contains an unknown node type.")
        if definition.get("availability") not in {"i18_1", "i18_2", "i18_6"}:
            raise AutomationValidationError("That visual node belongs to a later I18 execution phase.")
        category = str(definition.get("category") or "").strip()
        if category not in VISUAL_CATEGORY_ORDER:
            raise AutomationValidationError("Visual flow contains an unsupported node category.")
        category_counts[category] += 1
        if category_counts[category] > int(VISUAL_MAX_PER_CATEGORY[category]):
            raise AutomationValidationError(f"Too many {category} nodes for the constrained visual compiler.")
        nodes_by_id[node_id] = {
            "id": node_id,
            "type": node_type,
            "category": category,
            "position": _finite_position(raw_node.get("position"), fallback=VISUAL_DEFAULT_POSITIONS[category]),
            "raw_config": dict(raw_node.get("config") or {}) if isinstance(raw_node.get("config"), dict) else {},
        }

    for required in VISUAL_REQUIRED_CATEGORIES:
        # "Then · Ask me first" is a complete terminal outcome. Keep Output in
        # the published compatibility constraints, but do not require a
        # redundant Output node when a confirmation-gated Proposal is present.
        if required == "output" and category_counts.get("proposal", 0) > 0:
            continue
        if category_counts.get(required, 0) < 1:
            raise AutomationValidationError(f"Visual flows require at least one {required} node.")
    if category_counts["trigger"] != 1:
        raise AutomationValidationError("Visual flows require exactly one Trigger node.")
    if category_counts["output"] == 0 and category_counts["proposal"] == 0:
        raise AutomationValidationError("Visual flows require a final Then step: either an Output or an Ask Me First proposal.")

    raw_edges = raw.get("edges")
    if not isinstance(raw_edges, list) or len(raw_edges) != len(raw_nodes) - 1 or len(raw_edges) > VISUAL_MAX_EDGES:
        raise AutomationValidationError("Connect every node into one linear flow before saving.")
    canonical_edges: list[dict[str, str]] = []
    pairs: set[tuple[str, str]] = set()
    edge_ids: set[str] = set()
    for index, raw_edge in enumerate(raw_edges):
        if not isinstance(raw_edge, dict):
            raise AutomationValidationError("Invalid visual flow connection.")
        source = _validate_visual_node_id(raw_edge.get("source"))
        target = _validate_visual_node_id(raw_edge.get("target"))
        if source not in nodes_by_id or target not in nodes_by_id:
            raise AutomationValidationError("Visual flow connection references a missing node.")
        if source == target:
            raise AutomationValidationError("Visual flow nodes cannot connect to themselves.")
        pair = (source, target)
        if pair in pairs:
            raise AutomationValidationError("Duplicate visual flow connection.")
        source_category = nodes_by_id[source]["category"]
        target_category = nodes_by_id[target]["category"]
        if (source_category, target_category) not in VISUAL_CONNECTION_RULES:
            raise AutomationValidationError(f"The visual flow builder does not allow {source_category} → {target_category} connections.")
        pairs.add(pair)
        edge_id = str(raw_edge.get("id") or f"edge-{index + 1}").strip()
        if not edge_id or len(edge_id) > VISUAL_NODE_ID_MAX or any(not (character.isalnum() or character in "-_") for character in edge_id):
            raise AutomationValidationError("Visual flow connection id is invalid.")
        if edge_id in edge_ids:
            raise AutomationValidationError("Visual flow connection ids must be unique.")
        edge_ids.add(edge_id)
        canonical_edges.append({"id": edge_id, "source": source, "target": target})

    if _graph_has_cycle(set(nodes_by_id), canonical_edges):
        raise AutomationValidationError("Visual flow cycles are not supported in the visual flow builder.")
    order = _linear_visual_order(set(nodes_by_id), canonical_edges)
    ordered_categories = [nodes_by_id[node_id]["category"] for node_id in order]
    if ordered_categories[0] != "trigger":
        raise AutomationValidationError("The visual flow must start with its Trigger node.")
    if "proposal" in ordered_categories and ordered_categories[-1] != "proposal":
        raise AutomationValidationError("An I9 proposal must be the final node in the visual flow builder.")
    if "output" in ordered_categories:
        output_index = ordered_categories.index("output")
        if any(category in {"context", "intelligence"} for category in ordered_categories[output_index + 1:]):
            raise AutomationValidationError("Context and Intelligence nodes must run before the Output node.")
        if "proposal" not in ordered_categories and ordered_categories[-1] != "output":
            raise AutomationValidationError("The Output node must be the final step unless it is followed by an Ask Me First proposal.")

    trigger_node_id = order[0]
    trigger_node = nodes_by_id[trigger_node_id]
    expected_trigger_node_type = _visual_node_type_for_trigger(trigger_type, authoritative_trigger_config)
    if trigger_node["type"] != expected_trigger_node_type:
        raise AutomationValidationError("Visual trigger does not match the authoritative I17 trigger configuration.")

    bound_intelligence_ids = [
        node_id
        for node_id in order
        if nodes_by_id[node_id]["category"] == "intelligence"
        and str((VISUAL_NODE_REGISTRY[nodes_by_id[node_id]["type"]].get("binding") or {}).get("action_type") or "")
    ]
    if not bound_intelligence_ids:
        raise AutomationValidationError("The visual flow builder requires at least one I17-backed Intelligence node as a safe storage anchor.")
    i17_anchor_node_id = bound_intelligence_ids[0]
    anchor_definition = VISUAL_NODE_REGISTRY[nodes_by_id[i17_anchor_node_id]["type"]]
    anchor_action_type = str((anchor_definition.get("binding") or {}).get("action_type") or "")
    if anchor_action_type != action_type:
        raise AutomationValidationError("The first I17-backed Intelligence node must match the authoritative action binding.")

    if category_counts["proposal"]:
        proposal_id = order[-1]
        previous_id = order[-2]
        if nodes_by_id[proposal_id]["category"] != "proposal":
            raise AutomationValidationError("The proposal node must be the final flow step.")
        previous_type = nodes_by_id[previous_id]["type"]
        previous_category = nodes_by_id[previous_id]["category"]
        # A proposal is itself a valid user-facing THEN outcome.  It may follow
        # an Intelligence step directly, or preserve the older explicit
        # Suggest Action -> Proposal shape for backwards compatibility.
        if previous_category == "output" and previous_type != "output.suggest_action":
            raise AutomationValidationError("An Ask Me First proposal can follow an Intelligence or condition step directly, or follow ‘Suggest what I should do next’. ")
        if previous_category not in {"intelligence", "condition", "output"}:
            raise AutomationValidationError("An Ask Me First proposal must follow a verified Intelligence result or condition gate.")

    knowledge_context_before: set[str] = set()
    seen_knowledge_context = False
    for node_id in order:
        if nodes_by_id[node_id]["type"] in {"context.document", "context.collection", "context.module"}:
            seen_knowledge_context = True
        if seen_knowledge_context:
            knowledge_context_before.add(node_id)
    for node_id in order:
        if nodes_by_id[node_id]["type"] == "intelligence.review_document" and node_id not in knowledge_context_before:
            raise AutomationValidationError("Review Knowledge requires a Document, Collection, or Module Context node earlier in the flow.")

    canonical_nodes: list[dict[str, Any]] = []
    for node_id in order:
        node = nodes_by_id[node_id]
        node_type = node["type"]
        category = node["category"]
        if category == "trigger":
            config = authoritative_trigger_config
            semantic_type = trigger_type
        elif category == "context":
            config = _canonical_context_config(
                node_type=node_type,
                raw=node["raw_config"],
                owner_id=owner_id,
                trigger_type=trigger_type,
                trigger_config=authoritative_trigger_config,
            )
            semantic_type = str((VISUAL_NODE_REGISTRY[node_type].get("compiler") or {}).get("capability") or node_type)
        elif category == "intelligence":
            config = _canonical_intelligence_config(
                node_type=node_type,
                raw=node["raw_config"],
                owner_id=owner_id,
                is_i17_anchor=node_id == i17_anchor_node_id,
                authoritative_action_type=action_type,
                authoritative_action_config=authoritative_action_config,
            )
            bound_action = str((VISUAL_NODE_REGISTRY[node_type].get("binding") or {}).get("action_type") or "")
            semantic_type = bound_action or str((VISUAL_NODE_REGISTRY[node_type].get("compiler") or {}).get("capability") or node_type)
        elif category == "condition":
            config = _canonical_condition_config(node_type=node_type, raw=node["raw_config"])
            semantic_type = str((VISUAL_NODE_REGISTRY[node_type].get("compiler") or {}).get("capability") or node_type)
        else:
            config = {}
            # Preserve the existing I17/I18.1 persisted delivery semantic while
            # keeping the compiler capability (`output.notify_me`) in the
            # registry/compiled plan.  This avoids breaking saved-flow/API
            # consumers that already treat Notify Me as an in-app notification.
            if node_type == "output.notify_me":
                semantic_type = "in_app_notification"
            else:
                semantic_type = str((VISUAL_NODE_REGISTRY[node_type].get("compiler") or {}).get("capability") or node_type)
        canonical_nodes.append({
            "id": node_id,
            "type": node_type,
            "category": category,
            "position": node["position"],
            "config": dict(config),
            "semantic_type": semantic_type,
        })

    edge_by_pair = {(edge["source"], edge["target"]): edge for edge in canonical_edges}
    ordered_edges = [edge_by_pair[(order[index], order[index + 1])] for index in range(len(order) - 1)]
    output_node_id = next((node_id for node_id in order if nodes_by_id[node_id]["category"] == "output"), order[-1])
    return {
        "version": VISUAL_FLOW_VERSION,
        "phase": VISUAL_FLOW_PHASE,
        "nodes": canonical_nodes,
        "edges": ordered_edges,
        "execution_binding": {
            "source": "I17_allowlisted_trigger_and_action",
            "graph_is_execution_source": False,
            "compiler_is_execution_source": True,
            "trigger_node_id": trigger_node_id,
            "action_node_id": i17_anchor_node_id,
            "i17_anchor_node_id": i17_anchor_node_id,
            "output_node_id": output_node_id,
            "rich_graph_execution_phase": "I18.6",
        },
        "safety": {
            "workspace_mutation": False,
            "delivery": "compiled_output_contract",
            "future_workspace_actions_require": "I9_confirmation",
            "arbitrary_code": False,
            "arbitrary_sql": False,
            "arbitrary_urls": False,
            "direct_model_access": False,
        },
    }


def automation_visual_graph(item: LifeOSAutomation) -> dict[str, Any]:
    try:
        return validate_visual_graph(
            item.visual_graph,
            trigger_type=item.trigger_type,
            trigger_config=item.trigger_config,
            action_type=item.action_type,
            action_config=item.action_config,
            owner_id=item.user_id,
        )
    except AutomationValidationError as error:
        raw = item.visual_graph if isinstance(item.visual_graph, dict) else {}
        raw_nodes = raw.get("nodes") if isinstance(raw, dict) else None
        rich_graph = isinstance(raw_nodes, list) and (
            len(raw_nodes) > 3
            or any(
                isinstance(node, dict)
                and (VISUAL_NODE_REGISTRY.get(str(node.get("type") or "")) or {}).get("availability") in {"i18_2", "i18_6"}
                for node in raw_nodes
            )
        )
        if rich_graph:
            # A previously valid rich flow may become stale if a referenced
            # project/document/module/collection is later deleted. Preserve the
            # saved canonical graph for repair, but mark it invalid and block all
            # execution instead of silently falling back to a different I17 flow.
            preserved = dict(raw)
            preserved["phase"] = VISUAL_FLOW_PHASE
            preserved["validation"] = {"valid": False, "error": str(error)[:500]}
            return preserved
        return default_visual_graph(
            trigger_type=item.trigger_type,
            trigger_config=item.trigger_config,
            action_type=item.action_type,
            action_config=item.action_config,
        )


def compile_automation_visual_flow(item: LifeOSAutomation) -> dict[str, Any]:
    graph = automation_visual_graph(item)
    try:
        plan = compile_visual_flow(
            graph=graph,
            node_registry=VISUAL_NODE_REGISTRY,
            trigger_type=item.trigger_type,
            trigger_config=item.trigger_config,
            action_type=item.action_type,
            action_config=item.action_config,
        )
    except AutomationFlowCompileError as error:
        # Persisted graph metadata must never be able to crash the I17 worker or
        # automation list endpoint. A malformed/tampered graph is represented as
        # a blocked plan and requires user repair before any execution path opens.
        return {
            "version": 1,
            "phase": VISUAL_FLOW_PHASE,
            "plan_id": f"invalid-{item.id}",
            "status": "invalid",
            "source": "backend_constrained_visual_compiler",
            "graph_version": int(graph.get("version") or VISUAL_FLOW_VERSION) if isinstance(graph, dict) else VISUAL_FLOW_VERSION,
            "graph_phase": str(graph.get("phase") or VISUAL_FLOW_PHASE) if isinstance(graph, dict) else VISUAL_FLOW_PHASE,
            "ordered_node_ids": [],
            "trigger": {},
            "steps": [],
            "i17_binding": {
                "trigger_type": item.trigger_type,
                "trigger_config": dict(item.trigger_config or {}),
                "action_type": item.action_type,
                "action_config": dict(item.action_config or {}),
                "compatible": False,
                "storage_anchor_only": True,
            },
            "execution": {
                "mode": "blocked_invalid",
                "run_now_available": False,
                "preview_available": False,
                "background_available": False,
                "required_next_phase": None,
                "scheduled_visual_workflows_phase": None,
            },
            "diagnostics": {
                "compiled": False,
                "validation_error": str(error)[:500],
            },
            "safety": {
                "workspace_mutation": False,
                "arbitrary_code": False,
                "arbitrary_sql": False,
                "arbitrary_urls": False,
                "direct_model_access": False,
                "important_workspace_actions_require": "I9_confirmation",
                "llm_direct_db_writes": False,
            },
        }
    validation = graph.get("validation") if isinstance(graph, dict) else None
    if isinstance(validation, dict) and validation.get("valid") is False:
        plan["status"] = "invalid"
        plan["execution"] = {
            "mode": "blocked_invalid",
            "run_now_available": False,
            "preview_available": False,
            "background_available": False,
            "required_next_phase": None,
            "scheduled_visual_workflows_phase": None,
        }
        plan["diagnostics"]["validation_error"] = str(validation.get("error") or "Saved flow is no longer valid.")
    else:
        plan["status"] = "compiled"
    return plan


def automation_execution_contract(item: LifeOSAutomation) -> dict[str, Any]:
    return dict(compile_automation_visual_flow(item)["execution"])


def automation_registry() -> dict[str, Any]:
    categories = [
        {"id": "trigger", "label": "Triggers", "description": "When the flow starts."},
        {"id": "context", "label": "Context", "description": "Explicit owned LifeOS scope compiled through approved context boundaries."},
        {"id": "intelligence", "label": "Intelligence", "description": "Approved LifeOS reasoning/review capabilities."},
        {"id": "condition", "label": "Conditions", "description": "Safe gates that can quietly stop a flow when the verified result does not need action."},
        {"id": "output", "label": "Output", "description": "Safe delivery of verified results."},
        {"id": "proposal", "label": "Safe action proposals", "description": "Compiled proposals only; I9 confirmation remains mandatory before any workspace mutation."},
    ]
    visual_nodes = [
        {"type": node_type, **definition}
        for node_type, definition in VISUAL_NODE_REGISTRY.items()
    ]
    return {
        "triggers": [
            {"type": key, **value}
            for key, value in TRIGGER_TYPES.items()
        ],
        "event_types": sorted(EVENT_TYPES),
        "actions": [
            {"type": key, **value}
            for key, value in ACTION_TYPES.items()
        ],
        "templates": [
            {
                "key": "morning_briefing",
                "name": "Morning intelligence briefing",
                "description": "Every morning, decide what actually deserves your attention across projects, deadlines, documents, study, and recent changes.",
                "trigger_type": "schedule_daily",
                "trigger_config": {"hour": 8, "minute": 0},
                "action_type": "today_briefing",
                "action_config": {},
            },
            {
                "key": "weekly_review",
                "name": "Weekly intelligence review",
                "description": "Once a week, combine project priorities with what changed and surface the strongest next focus.",
                "trigger_type": "schedule_weekly",
                "trigger_config": {"weekday": 6, "hour": 18, "minute": 0},
                "action_type": "portfolio_review",
                "action_config": {},
            },
            {
                "key": "risk_escalation",
                "name": "Project risk escalation",
                "description": "Check daily for compound risk patterns instead of sending another simple deadline reminder.",
                "trigger_type": "schedule_daily",
                "trigger_config": {"hour": 17, "minute": 30},
                "action_type": "risk_escalation",
                "action_config": {},
            },
            {
                "key": "unhandled_followup",
                "name": "Unhandled document follow-up",
                "description": "Check whether current document risks/actions still lack a confirmed task or note follow-up.",
                "trigger_type": "schedule_daily",
                "trigger_config": {"hour": 18, "minute": 0},
                "action_type": "unhandled_followup",
                "action_config": {},
            },
        ],
        "visual_templates": [
            {
                "key": "visual_morning_focus",
                "name": "Morning focus flow",
                "description": "Build Today context, rank priorities, and notify you every morning.",
                "trigger_type": "schedule_daily",
                "trigger_config": {"hour": 8, "minute": 0},
                "action_type": "today_briefing",
                "action_config": {},
                "visual_graph": {
                    "version": VISUAL_FLOW_VERSION, "phase": VISUAL_FLOW_PHASE,
                    "nodes": [
                        {"id": "trigger-1", "type": "trigger.schedule_daily", "category": "trigger", "position": {"x": 60, "y": 190}, "config": {"hour": 8, "minute": 0}},
                        {"id": "context-1", "type": "context.all_lifeos", "category": "context", "position": {"x": 330, "y": 190}, "config": {}},
                        {"id": "intelligence-1", "type": "intelligence.today_briefing", "category": "intelligence", "position": {"x": 600, "y": 190}, "config": {}},
                        {"id": "intelligence-2", "type": "intelligence.rank_priorities", "category": "intelligence", "position": {"x": 890, "y": 190}, "config": {}},
                        {"id": "output-1", "type": "output.notify_me", "category": "output", "position": {"x": 1180, "y": 190}, "config": {}},
                    ],
                    "edges": [
                        {"id": "edge-1", "source": "trigger-1", "target": "context-1"},
                        {"id": "edge-2", "source": "context-1", "target": "intelligence-1"},
                        {"id": "edge-3", "source": "intelligence-1", "target": "intelligence-2"},
                        {"id": "edge-4", "source": "intelligence-2", "target": "output-1"},
                    ],
                },
            },
            {
                "key": "visual_weekly_risk",
                "name": "Weekly risk review",
                "description": "Review the workspace, evaluate compound risk, and notify you once a week.",
                "trigger_type": "schedule_weekly",
                "trigger_config": {"weekday": 6, "hour": 18, "minute": 0},
                "action_type": "portfolio_review",
                "action_config": {},
                "visual_graph": {
                    "version": VISUAL_FLOW_VERSION, "phase": VISUAL_FLOW_PHASE,
                    "nodes": [
                        {"id": "trigger-1", "type": "trigger.schedule_weekly", "category": "trigger", "position": {"x": 60, "y": 190}, "config": {"weekday": 6, "hour": 18, "minute": 0}},
                        {"id": "context-1", "type": "context.all_lifeos", "category": "context", "position": {"x": 330, "y": 190}, "config": {}},
                        {"id": "intelligence-1", "type": "intelligence.portfolio_review", "category": "intelligence", "position": {"x": 600, "y": 190}, "config": {}},
                        {"id": "intelligence-2", "type": "intelligence.detect_risks", "category": "intelligence", "position": {"x": 890, "y": 190}, "config": {}},
                        {"id": "output-1", "type": "output.notify_me", "category": "output", "position": {"x": 1180, "y": 190}, "config": {}},
                    ],
                    "edges": [
                        {"id": "edge-1", "source": "trigger-1", "target": "context-1"},
                        {"id": "edge-2", "source": "context-1", "target": "intelligence-1"},
                        {"id": "edge-3", "source": "intelligence-1", "target": "intelligence-2"},
                        {"id": "edge-4", "source": "intelligence-2", "target": "output-1"},
                    ],
                },
            },
            {
                "key": "visual_quiet_risk_alert",
                "name": "Quiet risk alert",
                "description": "Check for meaningful risk each day, but only notify you when the verified result actually needs attention.",
                "trigger_type": "schedule_daily",
                "trigger_config": {"hour": 17, "minute": 30},
                "action_type": "risk_escalation",
                "action_config": {},
                "visual_graph": {
                    "version": VISUAL_FLOW_VERSION, "phase": VISUAL_FLOW_PHASE,
                    "nodes": [
                        {"id": "trigger-1", "type": "trigger.schedule_daily", "category": "trigger", "position": {"x": 60, "y": 190}, "config": {"hour": 17, "minute": 30}},
                        {"id": "context-1", "type": "context.all_lifeos", "category": "context", "position": {"x": 330, "y": 190}, "config": {}},
                        {"id": "intelligence-1", "type": "intelligence.detect_risks", "category": "intelligence", "position": {"x": 600, "y": 190}, "config": {}},
                        {"id": "condition-1", "type": "condition.attention_needed", "category": "condition", "position": {"x": 860, "y": 190}, "config": {"minimum_attention": "medium"}},
                        {"id": "output-1", "type": "output.notify_me", "category": "output", "position": {"x": 1120, "y": 190}, "config": {}},
                    ],
                    "edges": [
                        {"id": "edge-1", "source": "trigger-1", "target": "context-1"},
                        {"id": "edge-2", "source": "context-1", "target": "intelligence-1"},
                        {"id": "edge-3", "source": "intelligence-1", "target": "condition-1"},
                        {"id": "edge-4", "source": "condition-1", "target": "output-1"},
                    ],
                },
            },
            {
                "key": "visual_custom_question",
                "name": "Custom LifeOS question",
                "description": "Ask your own read-only LifeOS question on demand and keep the verified answer in run history.",
                "trigger_type": "manual",
                "trigger_config": {},
                "action_type": "custom_ask",
                "action_config": {"instruction": "What deserves my attention right now, and why?"},
                "visual_graph": {
                    "version": VISUAL_FLOW_VERSION, "phase": VISUAL_FLOW_PHASE,
                    "nodes": [
                        {"id": "trigger-1", "type": "trigger.manual_run", "category": "trigger", "position": {"x": 60, "y": 190}, "config": {}},
                        {"id": "context-1", "type": "context.all_lifeos", "category": "context", "position": {"x": 330, "y": 190}, "config": {}},
                        {"id": "intelligence-1", "type": "intelligence.ask_lifeos", "category": "intelligence", "position": {"x": 600, "y": 190}, "config": {"instruction": "What deserves my attention right now, and why?"}},
                        {"id": "output-1", "type": "output.save_review_result", "category": "output", "position": {"x": 860, "y": 190}, "config": {}},
                    ],
                    "edges": [
                        {"id": "edge-1", "source": "trigger-1", "target": "context-1"},
                        {"id": "edge-2", "source": "context-1", "target": "intelligence-1"},
                        {"id": "edge-3", "source": "intelligence-1", "target": "output-1"},
                    ],
                },
            },
            {
                "key": "visual_manual_review",
                "name": "Manual workspace review",
                "description": "Run a workspace review and What Changed analysis only when you explicitly ask.",
                "trigger_type": "manual",
                "trigger_config": {},
                "action_type": "portfolio_review",
                "action_config": {},
                "visual_graph": {
                    "version": VISUAL_FLOW_VERSION, "phase": VISUAL_FLOW_PHASE,
                    "nodes": [
                        {"id": "trigger-1", "type": "trigger.manual_run", "category": "trigger", "position": {"x": 60, "y": 190}, "config": {}},
                        {"id": "context-1", "type": "context.recent_activity", "category": "context", "position": {"x": 330, "y": 190}, "config": {"window": "week"}},
                        {"id": "intelligence-1", "type": "intelligence.portfolio_review", "category": "intelligence", "position": {"x": 600, "y": 190}, "config": {}},
                        {"id": "intelligence-2", "type": "intelligence.what_changed", "category": "intelligence", "position": {"x": 890, "y": 190}, "config": {}},
                        {"id": "output-1", "type": "output.save_review_result", "category": "output", "position": {"x": 1180, "y": 190}, "config": {}},
                    ],
                    "edges": [
                        {"id": "edge-1", "source": "trigger-1", "target": "context-1"},
                        {"id": "edge-2", "source": "context-1", "target": "intelligence-1"},
                        {"id": "edge-3", "source": "intelligence-1", "target": "intelligence-2"},
                        {"id": "edge-4", "source": "intelligence-2", "target": "output-1"},
                    ],
                },
            },
        ],
        "limits": {"max_automations_per_user": MAX_AUTOMATIONS_PER_USER},
        "visual_flow": {
            "version": VISUAL_FLOW_VERSION,
            "phase": VISUAL_FLOW_PHASE,
            "node_order": list(VISUAL_CATEGORY_ORDER),
            "delivery_type": "in_app_notification",
            "connections_fixed": False,
            "layout_persisted": True,
            "execution_source": "I17_allowlisted_trigger_and_action",
            "compiler_source": "backend_constrained_visual_compiler",
            "graph_is_execution_source": False,
            "compiler_is_execution_source": True,
            "categories": categories,
            "nodes": visual_nodes,
            "connection_rules": [
                {"source": source, "target": target}
                for source, target in sorted(VISUAL_CONNECTION_RULES)
            ],
            "constraints": {
                "max_nodes": VISUAL_MAX_NODES,
                "max_edges": VISUAL_MAX_EDGES,
                "required_categories": list(VISUAL_REQUIRED_CATEGORIES),
                "max_per_category": dict(VISUAL_MAX_PER_CATEGORY),
                "cycles_allowed": False,
                "branching_allowed": False,
                "compiler_available": True,
                "rich_graph_execution_available": True,
                "rich_graph_execution_phase": "I18.6",
                "rich_graph_background_phase": "I18.6",
            },
        },
        "safety": {
            "arbitrary_code": False,
            "arbitrary_sql": False,
            "arbitrary_urls": False,
            "workspace_mutation": False,
            "i9_confirmation_required_for_future_mutations": True,
            "background_execution_available": True,
            "single_worker_v1": True,
        },
    }

def _clean_name(value: Any) -> str:
    name = str(value or "").strip()
    if not name:
        raise AutomationValidationError("Automation name is required.")
    if len(name) > 160:
        raise AutomationValidationError("Automation name is too long.")
    return name


def _timezone(name: Any) -> ZoneInfo:
    zone_name = str(name or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(zone_name)
    except ZoneInfoNotFoundError as error:
        raise AutomationValidationError("Use a valid IANA timezone, for example Africa/Cairo or UTC.") from error


def _int_between(value: Any, minimum: int, maximum: int, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise AutomationValidationError(f"{label} must be a number.") from error
    if parsed < minimum or parsed > maximum:
        raise AutomationValidationError(f"{label} must be between {minimum} and {maximum}.")
    return parsed


def validate_trigger(trigger_type: Any, raw: Any) -> tuple[str, dict[str, Any]]:
    kind = str(trigger_type or "").strip()
    # I18 visual nodes use ``trigger.manual_run`` while the authoritative I17
    # storage value is ``manual``. Accept the user-facing/API alias here and
    # immediately canonicalize it so the database/executor still has one
    # authoritative trigger type.
    if kind == "manual_run":
        kind = "manual"
    if kind not in TRIGGER_TYPES:
        raise AutomationValidationError("Unsupported automation trigger.")
    config = raw if isinstance(raw, dict) else {}

    if kind == "schedule_daily":
        return kind, {
            "hour": _int_between(config.get("hour", 8), 0, 23, "Hour"),
            "minute": _int_between(config.get("minute", 0), 0, 59, "Minute"),
        }
    if kind == "schedule_weekly":
        return kind, {
            "weekday": _int_between(config.get("weekday", 0), 0, 6, "Weekday"),
            "hour": _int_between(config.get("hour", 8), 0, 23, "Hour"),
            "minute": _int_between(config.get("minute", 0), 0, 59, "Minute"),
        }
    if kind == "manual":
        return kind, {}

    event_type = str(config.get("event_type") or "").strip()
    if event_type not in EVENT_TYPES:
        raise AutomationValidationError("Unsupported LifeOS event trigger.")
    return kind, {"event_type": event_type}


def validate_action(*, owner_id: int, action_type: Any, raw: Any) -> tuple[str, dict[str, Any]]:
    kind = str(action_type or "").strip()
    if kind not in ACTION_TYPES:
        raise AutomationValidationError("Unsupported automation action.")
    config = raw if isinstance(raw, dict) else {}

    if kind == "project_review":
        project_id = _int_between(config.get("project_id"), 1, 2_147_483_647, "Project")
        project = Project.query.filter_by(id=project_id, user_id=owner_id).first()
        if project is None:
            raise AutomationValidationError("Selected project was not found.")
        return kind, {"project_id": project_id}

    if kind == "custom_ask":
        instruction = " ".join(str(config.get("instruction") or "").split())
        if len(instruction) < 3:
            raise AutomationValidationError("Ask LifeOS needs a short instruction or question.")
        if len(instruction) > 600:
            raise AutomationValidationError("Ask LifeOS instructions can contain at most 600 characters.")
        return kind, {"instruction": instruction}

    # The other V1 actions accept no arbitrary payload.
    return kind, {}


def calculate_next_run_at(
    *,
    trigger_type: str,
    trigger_config: dict[str, Any],
    timezone_name: str,
    now: datetime | None = None,
) -> datetime | None:
    if trigger_type in {"event", "manual"}:
        return None

    zone = _timezone(timezone_name)
    if now is None:
        current_utc = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        current_utc = now.replace(tzinfo=timezone.utc)
    else:
        current_utc = now.astimezone(timezone.utc)
    local_now = current_utc.astimezone(zone)

    hour = int(trigger_config["hour"])
    minute = int(trigger_config["minute"])
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if trigger_type == "schedule_daily":
        if candidate <= local_now:
            candidate += timedelta(days=1)
    elif trigger_type == "schedule_weekly":
        target_weekday = int(trigger_config["weekday"])
        days = (target_weekday - local_now.weekday()) % 7
        candidate += timedelta(days=days)
        if candidate <= local_now:
            candidate += timedelta(days=7)
    else:
        raise AutomationValidationError("Unsupported schedule trigger.")

    # Persist schedule timestamps in naive UTC, matching existing LifeOS timestamp conventions.
    return candidate.astimezone(timezone.utc).replace(tzinfo=None)


def event_matches_automation(automation: LifeOSAutomation, event: LifeOSIntelligenceEvent) -> bool:
    if automation.trigger_type != "event" or not automation.enabled:
        return False
    if event.user_id != automation.user_id:
        return False
    return automation.trigger_config.get("event_type") == event.event_type


def _owned_automation(*, owner_id: int, automation_id: int) -> LifeOSAutomation:
    automation = LifeOSAutomation.query.filter_by(id=automation_id, user_id=owner_id).first()
    if automation is None:
        raise AutomationNotFoundError("Automation not found.")
    return automation


def automation_to_dict(item: LifeOSAutomation) -> dict[str, Any]:
    graph = automation_visual_graph(item)
    compiled_plan = compile_automation_visual_flow(item)
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "enabled": bool(item.enabled),
        "status": item.status,
        "trigger": {"type": item.trigger_type, "config": item.trigger_config},
        "action": {"type": item.action_type, "config": item.action_config},
        "visual_graph": graph,
        "compiled_plan": compiled_plan,
        "execution": dict(compiled_plan["execution"]),
        "timezone": item.timezone,
        "next_run_at": item.next_run_at.isoformat() if item.next_run_at else None,
        "last_run_at": item.last_run_at.isoformat() if item.last_run_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "safety": {"workspace_mutation": False, "confirmation_boundary": "I9"},
    }


def automation_run_to_dict(item: LifeOSAutomationRun) -> dict[str, Any]:
    return {
        "id": item.id,
        "automation_id": item.automation_id,
        "status": item.status,
        "trigger_source": item.trigger_source,
        "event_id": item.event_id,
        "dry_run": bool(item.dry_run),
        "output": item.output,
        "error_message": item.error_message,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "finished_at": item.finished_at.isoformat() if item.finished_at else None,
    }


def list_owned_automations(*, owner_id: int) -> tuple[LifeOSAutomation, ...]:
    return tuple(
        LifeOSAutomation.query.filter_by(user_id=owner_id)
        .order_by(LifeOSAutomation.created_at.desc(), LifeOSAutomation.id.desc())
        .all()
    )


def compile_owned_visual_flow_draft(
    *,
    owner_id: int,
    trigger_type: Any,
    trigger_config: Any,
    action_type: Any,
    action_config: Any,
    visual_graph: Any,
) -> dict[str, Any]:
    """Validate and compile a draft graph without persisting or executing it."""

    trigger_kind, trigger = validate_trigger(trigger_type, trigger_config)
    action_kind, action = validate_action(owner_id=owner_id, action_type=action_type, raw=action_config)
    graph = validate_visual_graph(
        visual_graph,
        trigger_type=trigger_kind,
        trigger_config=trigger,
        action_type=action_kind,
        action_config=action,
        owner_id=owner_id,
    )
    try:
        plan = compile_visual_flow(
            graph=graph,
            node_registry=VISUAL_NODE_REGISTRY,
            trigger_type=trigger_kind,
            trigger_config=trigger,
            action_type=action_kind,
            action_config=action,
        )
    except AutomationFlowCompileError as error:
        raise AutomationValidationError(str(error)) from error
    plan["status"] = "compiled"
    return {"visual_graph": graph, "compiled_plan": plan}


def create_owned_automation(
    *,
    owner_id: int,
    name: Any,
    description: Any = None,
    enabled: bool = False,
    trigger_type: Any,
    trigger_config: Any,
    action_type: Any,
    action_config: Any,
    timezone_name: Any = "UTC",
    visual_graph: Any = None,
) -> LifeOSAutomation:
    if LifeOSAutomation.query.filter_by(user_id=owner_id).count() >= MAX_AUTOMATIONS_PER_USER:
        raise AutomationValidationError("Automation limit reached.")
    clean_name = _clean_name(name)
    if LifeOSAutomation.query.filter_by(user_id=owner_id, name=clean_name).first() is not None:
        raise AutomationValidationError("An automation with that name already exists.")

    trigger_kind, trigger = validate_trigger(trigger_type, trigger_config)
    action_kind, action = validate_action(owner_id=owner_id, action_type=action_type, raw=action_config)
    graph = validate_visual_graph(
        visual_graph,
        trigger_type=trigger_kind,
        trigger_config=trigger,
        action_type=action_kind,
        action_config=action,
        owner_id=owner_id,
    )
    try:
        compiled_plan = compile_visual_flow(
            graph=graph,
            node_registry=VISUAL_NODE_REGISTRY,
            trigger_type=trigger_kind,
            trigger_config=trigger,
            action_type=action_kind,
            action_config=action,
        )
    except AutomationFlowCompileError as error:
        raise AutomationValidationError(str(error)) from error
    execution = compiled_plan["execution"]
    if bool(enabled) and not bool(execution.get("background_available")):
        raise AutomationValidationError("Manual-only visual flows cannot be enabled for background execution.")
    zone = _timezone(timezone_name)
    zone_name = zone.key
    now = datetime.utcnow()
    next_run_at = (
        calculate_next_run_at(
            trigger_type=trigger_kind,
            trigger_config=trigger,
            timezone_name=zone_name,
            now=now,
        )
        if bool(execution.get("background_available"))
        else None
    )

    item = LifeOSAutomation(
        user_id=owner_id,
        name=clean_name,
        description=str(description or "").strip() or None,
        enabled=bool(enabled),
        trigger_type=trigger_kind,
        trigger_config_json=json.dumps(trigger, ensure_ascii=False, sort_keys=True),
        action_type=action_kind,
        action_config_json=json.dumps(action, ensure_ascii=False, sort_keys=True),
        visual_graph_json=json.dumps(graph, ensure_ascii=False, sort_keys=True),
        timezone=zone_name,
        status="ready",
        next_run_at=next_run_at,
        created_at=now,
        updated_at=now,
    )
    db.session.add(item)
    db.session.commit()
    return item


def update_owned_automation(*, owner_id: int, automation_id: int, payload: dict[str, Any]) -> LifeOSAutomation:
    item = _owned_automation(owner_id=owner_id, automation_id=automation_id)

    if "name" in payload:
        clean_name = _clean_name(payload.get("name"))
        duplicate = LifeOSAutomation.query.filter(
            LifeOSAutomation.user_id == owner_id,
            LifeOSAutomation.name == clean_name,
            LifeOSAutomation.id != item.id,
        ).first()
        if duplicate is not None:
            raise AutomationValidationError("An automation with that name already exists.")
        item.name = clean_name
    if "description" in payload:
        item.description = str(payload.get("description") or "").strip() or None

    trigger_kind, trigger = validate_trigger(
        payload.get("trigger_type", item.trigger_type),
        payload.get("trigger_config", item.trigger_config),
    )
    action_kind, action = validate_action(
        owner_id=owner_id,
        action_type=payload.get("action_type", item.action_type),
        raw=payload.get("action_config", item.action_config),
    )
    graph = validate_visual_graph(
        payload.get("visual_graph", item.visual_graph),
        trigger_type=trigger_kind,
        trigger_config=trigger,
        action_type=action_kind,
        action_config=action,
        owner_id=owner_id,
    )
    try:
        compiled_plan = compile_visual_flow(
            graph=graph,
            node_registry=VISUAL_NODE_REGISTRY,
            trigger_type=trigger_kind,
            trigger_config=trigger,
            action_type=action_kind,
            action_config=action,
        )
    except AutomationFlowCompileError as error:
        raise AutomationValidationError(str(error)) from error
    execution = compiled_plan["execution"]
    effective_enabled = bool(payload.get("enabled", item.enabled))
    if effective_enabled and not bool(execution.get("background_available")):
        raise AutomationValidationError("Manual-only visual flows cannot be enabled for background execution.")
    zone = _timezone(payload.get("timezone", item.timezone))

    item.trigger_type = trigger_kind
    item.trigger_config_json = json.dumps(trigger, ensure_ascii=False, sort_keys=True)
    item.action_type = action_kind
    item.action_config_json = json.dumps(action, ensure_ascii=False, sort_keys=True)
    item.visual_graph_json = json.dumps(graph, ensure_ascii=False, sort_keys=True)
    item.timezone = zone.key
    item.enabled = effective_enabled
    item.status = "ready"
    item.next_run_at = (
        calculate_next_run_at(
            trigger_type=item.trigger_type,
            trigger_config=item.trigger_config,
            timezone_name=item.timezone,
            now=datetime.utcnow(),
        )
        if bool(execution.get("background_available"))
        else None
    )
    item.updated_at = datetime.utcnow()
    db.session.commit()
    return item


def clear_owned_automation_error(*, owner_id: int, automation_id: int) -> LifeOSAutomation:
    """Clear the visible error state without deleting immutable run history."""
    item = _owned_automation(owner_id=owner_id, automation_id=automation_id)
    plan = compile_automation_visual_flow(item)
    if plan.get("execution", {}).get("mode") == "blocked_invalid":
        raise AutomationValidationError("Repair and save the invalid visual flow before clearing its error state.")
    item.status = "ready"
    item.updated_at = datetime.utcnow()
    db.session.commit()
    return item


def delete_owned_automation(*, owner_id: int, automation_id: int) -> None:
    item = _owned_automation(owner_id=owner_id, automation_id=automation_id)
    db.session.delete(item)
    db.session.commit()


def list_owned_automation_runs(*, owner_id: int, automation_id: int, limit: int = 20) -> tuple[LifeOSAutomationRun, ...]:
    _owned_automation(owner_id=owner_id, automation_id=automation_id)
    bounded = max(1, min(int(limit or 20), MAX_RUN_HISTORY))
    return tuple(
        LifeOSAutomationRun.query.filter_by(user_id=owner_id, automation_id=automation_id)
        .order_by(LifeOSAutomationRun.started_at.desc(), LifeOSAutomationRun.id.desc())
        .limit(bounded)
        .all()
    )


def build_owned_automation_output(
    *,
    owner_id: int,
    automation: LifeOSAutomation,
    event_id: int | None = None,
) -> dict[str, Any]:
    """Run one reviewed, read-only intelligence action.

    The result may ask I17 to create a *notification metadata event*, but this
    function itself never mutates user workspace resources.
    """

    if automation.action_type == "today_briefing":
        return build_today_briefing_output(owner_id=owner_id)
    if automation.action_type == "portfolio_review":
        return build_weekly_review_output(owner_id=owner_id)
    if automation.action_type == "project_review":
        project_id = int(automation.action_config["project_id"])
        from services.project_review_agent_service import run_owned_project_review_agent
        result = run_owned_project_review_agent(project_id=project_id, owner_id=owner_id).to_dict(include_diagnostics=False)
        priorities = result.get("priorities", [])
        title = f"Project review ready: {result.get('project_title') or 'Project'}"
        summary = f"Reviewed {result.get('project_title') or 'the project'} and found {len(priorities)} ranked priorit{'y' if len(priorities) == 1 else 'ies'}."
        if priorities:
            summary += f" Top focus: {priorities[0].get('title')}."
        return {
            "kind": "project_review",
            "project_id": project_id,
            "title": title,
            "summary": summary,
            "attention_level": result.get("attention_level"),
            "priorities": priorities[:5],
            "priority_count": len(priorities),
            "verified_from_state": True,
            "read_only": True,
            "notification": {
                "should_notify": True,
                "event_type": "automation.project_review_ready",
                "severity": "high" if result.get("attention_level") == "high" else "medium" if result.get("attention_level") == "medium" else "info",
                "title": title,
                "message": summary,
                "dedupe_scope": "run",
                "action_label": "Open project",
                "action_href": f"/projects/{project_id}",
                "ask_query": f"Review my project #{project_id} and tell me what needs attention",
            },
        }
    if automation.action_type == "risk_escalation":
        return build_risk_escalation_output(owner_id=owner_id)
    if automation.action_type == "unhandled_followup":
        return build_unhandled_followup_output(owner_id=owner_id)
    if automation.action_type == "attention_notice":
        if event_id is None:
            return {
                "kind": "event_context_review",
                "title": "Event context review is ready",
                "summary": "This event automation is ready. A real event-triggered run will review the verified I14 event in project context.",
                "verified_from_state": True,
                "read_only": True,
                "notification": {"should_notify": False},
            }
        event = LifeOSIntelligenceEvent.query.filter_by(id=event_id, user_id=owner_id).first()
        if event is None:
            raise AutomationValidationError("Trigger event was not found.")
        if not event_matches_automation(automation, event):
            raise AutomationValidationError("The event does not match this automation trigger.")
        return build_event_context_review_output(owner_id=owner_id, event=event)
    raise AutomationValidationError("Unsupported automation action.")


def _preview_output(*, owner_id: int, automation: LifeOSAutomation, event_id: int | None = None) -> dict[str, Any]:
    execution = automation_execution_contract(automation)
    if execution.get("mode") == "compiled_i17":
        from services.automation_flow_execution_service import execute_compiled_visual_flow
        output = execute_compiled_visual_flow(
            owner_id=owner_id,
            automation=automation,
            compiled_plan=compile_automation_visual_flow(automation),
            event_id=event_id,
            dry_run=True,
        )
        # Keep the compiled runtime's canonical root-level ``flow_trace`` while
        # also exposing the stable preview/UI compatibility contract used by
        # I18 consumers.  This is an adapter only; execution and audit data
        # remain owned by the existing I17 compiled runtime.
        trace = output.get("flow_trace")
        if isinstance(trace, list):
            output = dict(output)
            output["visual_flow"] = {
                "status": "succeeded",
                "node_runs": trace,
                "error": None,
                "flow_halted": bool(output.get("flow_halted")),
                "halt_reason": output.get("halt_reason"),
            }
        return output
    return build_owned_automation_output(owner_id=owner_id, automation=automation, event_id=event_id)


def preview_owned_automation(
    *,
    owner_id: int,
    automation_id: int,
    event_id: int | None = None,
) -> AutomationPreviewResult:
    automation = _owned_automation(owner_id=owner_id, automation_id=automation_id)
    execution = automation_execution_contract(automation)
    if not bool(execution.get("preview_available")):
        if execution.get("mode") == "blocked_invalid":
            raise AutomationValidationError("This visual flow is invalid and must be repaired before it can be previewed.")
        raise AutomationValidationError("This visual flow cannot be previewed until its validation errors are repaired.")
    now = datetime.utcnow()
    run = LifeOSAutomationRun(
        automation_id=automation.id,
        user_id=owner_id,
        status="running",
        trigger_source="preview",
        event_id=event_id,
        dry_run=True,
        started_at=now,
    )
    db.session.add(run)
    db.session.flush()
    try:
        output = _preview_output(owner_id=owner_id, automation=automation, event_id=event_id)
        run.status = "succeeded"
        run.output_json = json.dumps(output, ensure_ascii=False, sort_keys=True, default=str)
        run.finished_at = datetime.utcnow()
        db.session.commit()
    except Exception as error:
        run.status = "failed"
        run.error_message = str(error)[:2000]
        audit_output = getattr(error, "audit_output", None)
        if callable(audit_output):
            run.output_json = json.dumps(audit_output(), ensure_ascii=False, sort_keys=True, default=str)
        run.finished_at = datetime.utcnow()
        db.session.commit()
        raise
    return AutomationPreviewResult(automation=automation, run=run, output=output)


def due_owned_schedule_automations(*, owner_id: int, now: datetime | None = None) -> tuple[LifeOSAutomation, ...]:
    effective_now = now or datetime.utcnow()
    items = LifeOSAutomation.query.filter(
        LifeOSAutomation.user_id == owner_id,
        LifeOSAutomation.enabled == true(),
        LifeOSAutomation.trigger_type.in_(("schedule_daily", "schedule_weekly")),
        LifeOSAutomation.next_run_at.isnot(None),
        LifeOSAutomation.next_run_at <= effective_now,
    ).order_by(LifeOSAutomation.next_run_at.asc()).all()
    return tuple(item for item in items if automation_execution_contract(item).get("background_available"))
