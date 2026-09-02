"""I18 — constrained compiler for LifeOS visual automation graphs.

This module is a compiler, not a second runtime. It consumes only the backend-
canonical graph and the backend-owned node registry, then produces a deterministic
execution plan made of approved LifeOS capability keys. It never executes SQL,
models, prompts, URLs, or workspace mutations.

I17 remains the authoritative runtime. Exact legacy-compatible flows use the
existing direct path; richer validated linear plans are executed by the I18
compiled-plan adapter through approved LifeOS services and the same I17 worker.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any


FLOW_PLAN_VERSION = 1
FLOW_PLAN_PHASE = "I18.6"


class AutomationFlowCompileError(ValueError):
    """Raised when a canonical graph cannot be compiled safely."""


def _linear_order(graph: dict[str, Any]) -> list[str]:
    nodes = graph.get("nodes") if isinstance(graph, dict) else None
    edges = graph.get("edges") if isinstance(graph, dict) else None
    if not isinstance(nodes, list) or not isinstance(edges, list) or not nodes:
        raise AutomationFlowCompileError("Visual flow is missing nodes or connections.")

    ids = [str(node.get("id") or "") for node in nodes if isinstance(node, dict)]
    if len(ids) != len(nodes) or any(not node_id for node_id in ids) or len(set(ids)) != len(ids):
        raise AutomationFlowCompileError("Visual flow node ids are invalid.")

    indegree = {node_id: 0 for node_id in ids}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in ids}
    for edge in edges:
        if not isinstance(edge, dict):
            raise AutomationFlowCompileError("Visual flow contains an invalid connection.")
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in indegree or target not in indegree:
            raise AutomationFlowCompileError("Visual flow connection references a missing node.")
        indegree[target] += 1
        outgoing[source].append(target)

    roots = [node_id for node_id, degree in indegree.items() if degree == 0]
    if len(roots) != 1:
        raise AutomationFlowCompileError("Compiled flows require exactly one root trigger.")
    if any(degree > 1 for degree in indegree.values()) or any(len(items) > 1 for items in outgoing.values()):
        raise AutomationFlowCompileError("LifeOS visual flows currently support one linear flow; branching and merging are intentionally disabled.")

    ordered: list[str] = []
    seen: set[str] = set()
    current: str | None = roots[0]
    while current is not None:
        if current in seen:
            raise AutomationFlowCompileError("Visual flow cycles are not supported.")
        seen.add(current)
        ordered.append(current)
        next_nodes = outgoing[current]
        current = next_nodes[0] if next_nodes else None

    if len(ordered) != len(ids):
        raise AutomationFlowCompileError("Every visual node must belong to one connected flow.")
    return ordered


def _semantic_plan_fingerprint(steps: list[dict[str, Any]], trigger: dict[str, Any], i17_binding: dict[str, Any]) -> str:
    payload = {
        "trigger": trigger,
        "steps": [
            {
                "node_type": step["node_type"],
                "category": step["category"],
                "capability": step["capability"],
                "config": step["config"],
                "confirmation_boundary": step.get("confirmation_boundary"),
            }
            for step in steps
        ],
        "i17_binding": i17_binding,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(raw.encode("utf-8")).hexdigest()[:24]


def compile_visual_flow(
    *,
    graph: dict[str, Any],
    node_registry: dict[str, dict[str, Any]],
    trigger_type: str,
    trigger_config: dict[str, Any],
    action_type: str,
    action_config: dict[str, Any],
) -> dict[str, Any]:
    """Compile a canonical graph into a deterministic approved execution plan."""

    order = _linear_order(graph)
    nodes_by_id = {
        str(node["id"]): node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and node.get("id") is not None
    }

    steps: list[dict[str, Any]] = []
    for index, node_id in enumerate(order):
        node = nodes_by_id[node_id]
        node_type = str(node.get("type") or "")
        definition = node_registry.get(node_type)
        if definition is None:
            raise AutomationFlowCompileError("Visual flow contains a node outside the approved registry.")
        compiler = definition.get("compiler")
        if not isinstance(compiler, dict) or not compiler.get("capability"):
            raise AutomationFlowCompileError(f"{definition.get('label') or node_type} has no approved compiler binding.")

        step = {
            "index": index,
            "node_id": node_id,
            "node_type": node_type,
            "category": str(definition.get("category") or node.get("category") or ""),
            "label": str(definition.get("label") or node_type),
            "capability": str(compiler["capability"]),
            "service_boundary": str(compiler.get("service_boundary") or "lifeos.approved_service"),
            "input_contract": str(compiler.get("input_contract") or "verified_lifeos_state"),
            "output_contract": str(compiler.get("output_contract") or "verified_result"),
            "config": dict(node.get("config") or {}),
            "read_only": bool(compiler.get("read_only", True)),
            "workspace_mutation": False,
        }
        confirmation = definition.get("confirmation_boundary") or compiler.get("confirmation_boundary")
        if confirmation:
            step["confirmation_boundary"] = str(confirmation)
            step["proposal_only"] = True
        steps.append(step)

    categories = [step["category"] for step in steps]
    direct_compatible = (
        len(steps) == 3
        and categories == ["trigger", "intelligence", "output"]
        and steps[0]["node_type"].startswith("trigger.")
        and steps[1]["node_type"].startswith("intelligence.")
        and steps[2]["node_type"] == "output.notify_me"
        and node_registry[steps[0]["node_type"]].get("availability") == "i18_1"
        and node_registry[steps[1]["node_type"]].get("availability") == "i18_1"
        and node_registry[steps[2]["node_type"]].get("availability") == "i18_1"
    )

    i17_binding = {
        "trigger_type": trigger_type,
        "trigger_config": dict(trigger_config),
        "action_type": action_type,
        "action_config": dict(action_config),
        "compatible": direct_compatible,
        "storage_anchor_only": not direct_compatible,
    }
    trigger_step = steps[0]
    plan_id = _semantic_plan_fingerprint(steps, trigger_step, i17_binding)

    return {
        "version": FLOW_PLAN_VERSION,
        "phase": FLOW_PLAN_PHASE,
        "plan_id": plan_id,
        "source": "backend_constrained_visual_compiler",
        "graph_version": int(graph.get("version") or 1),
        "graph_phase": str(graph.get("phase") or FLOW_PLAN_PHASE),
        "ordered_node_ids": order,
        "trigger": {
            "node_id": trigger_step["node_id"],
            "node_type": trigger_step["node_type"],
            "capability": trigger_step["capability"],
            "config": dict(trigger_step["config"]),
        },
        "steps": steps,
        "i17_binding": i17_binding,
        "execution": {
            "mode": "i17_direct" if direct_compatible else "compiled_i17",
            "run_now_available": True,
            "preview_available": True,
            "background_available": (trigger_type in {"schedule_daily", "schedule_weekly", "event"}),
            "required_next_phase": None,
            "scheduled_visual_workflows_phase": None,
        },
        "diagnostics": {
            "node_count": len(steps),
            "edge_count": len(graph.get("edges") or []),
            "linear": True,
            "cycles": False,
            "branching": False,
            "compiled": True,
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
