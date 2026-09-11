"""General request understanding + capability routing for Ask LifeOS.

This layer classifies *how to solve* a request rather than creating a growing
list of domain-specific intents. Existing deterministic LifeOS routes still win
for exact workspace facts; this profile is used for open-ended reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import re
from typing import Any

from ai.provider_router import AIProviderRouterError, generate_text as route_ai_text
from services.ai_service import AIServiceError, get_ai_configuration


TASK_TYPES = frozenset({
    "factual", "explain", "analyze", "advise", "troubleshoot", "decide",
    "prioritize", "plan", "compare", "summarize", "create", "execute",
    "calculate", "research",
})
COMPLEXITIES = frozenset({"simple", "reasoning", "multi_step"})
KNOWLEDGE_SCOPES = frozenset({"general", "workspace", "documents", "workspace_plus_general", "mixed"})
ACTION_MODES = frozenset({"read_only", "recommendation", "mutation_requested"})

MAX_PUBLIC_WEB_QUERY_CHARACTERS = 420
MAX_CALCULATOR_EXPRESSION_CHARACTERS = 500


@dataclass(frozen=True)
class RequestProfile:
    task_type: str
    complexity: str
    knowledge_scope: str
    needs_workspace: bool
    needs_rag: bool
    needs_web: bool
    needs_calculator: bool
    needs_code: bool
    action_mode: str
    web_query: str | None = None
    calculator_expression: str | None = None
    source: str = "deterministic"

    def to_dict(self, *, public: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "task_type": self.task_type,
            "complexity": self.complexity,
            "knowledge_scope": self.knowledge_scope,
            "needs_workspace": self.needs_workspace,
            "needs_rag": self.needs_rag,
            "needs_web": self.needs_web,
            "needs_calculator": self.needs_calculator,
            "needs_code": self.needs_code,
            "action_mode": self.action_mode,
        }
        if not public:
            result.update({
                "web_query": self.web_query,
                "calculator_expression": self.calculator_expression,
                "source": self.source,
            })
        return result


class RequestUnderstandingError(RuntimeError):
    pass


def _normalized(query: str) -> str:
    return " ".join(str(query or "").casefold().split())


def _has(text: str, values: tuple[str, ...]) -> bool:
    return any(value in text for value in values)


def _looks_like_math(text: str) -> bool:
    if _has(text, ("calculate", "compute", "work out", "solve the equation", "percentage", "percent", "ratio", "average", "probability", "how much would", "how much will")):
        return True
    return bool(re.search(r"(?:\d[\d,.]*\s*[+\-*/^%]\s*\d)|(?:\d+(?:\.\d+)?\s*%)", text))


def _looks_like_code(text: str) -> bool:
    # A technology name alone (for example "Flask" in "official Flask docs")
    # is not a request for generated code. Detect code capability from the user's
    # requested operation/error shape instead of accumulating framework keywords.
    return _has(text, (
        "write code", "show code", "show me code", "code example", "give me code",
        "with code", "with python code", "with javascript code", "with typescript code",
        "with sql code", "using python code", "using javascript code", "using typescript code",
        "write python", "write javascript", "write typescript", "write sql",
        "implement this", "implement a ", "implement an ", "write a function",
        "write a class", "write a query", "pseudocode", "algorithm for",
        "fix this code", "debug this code", "stack trace", "traceback",
        "compile error", "runtime error", "syntax error",
    ))


def _looks_like_web(text: str) -> bool:
    return _has(text, (
        "search the web", "search online", "browse the web", "browse online", "look up online",
        "look it up", "latest", "current price", "current pricing", "today's", "today ",
        "right now", "recent news", "news about", "official docs", "official documentation",
        "release notes", "current version", "as of 20", "up to date", "up-to-date",
    ))


def _looks_like_mutation(text: str) -> bool:
    return _has(text, (
        "create a task", "create task", "add a task", "save this", "save a note", "create a note",
        "update the task", "change the task", "delete the task", "schedule this", "mark as complete",
        "change my project", "update my project",
    ))


def _heuristic_task_type(text: str) -> tuple[str, float]:
    # These are speech-act patterns, not domain keywords. They remain stable as
    # LifeOS gains new subjects/capabilities.
    rules: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("calculate", ("calculate", "compute", "solve the equation", "work out")),
        ("research", ("search the web", "search online", "browse", "look up", "research")),
        ("troubleshoot", ("debug", "why is", "why does", "not working", "error", "failing", "broken", "fix this")),
        ("compare", ("compare", "difference between", " vs ", "versus")),
        # More-specific guidance speech acts must win before the broad
        # ``should i`` decision marker. Otherwise phrases such as
        # "what should I do next", "how should I prepare", and
        # "what should I do to deploy this project" are all incorrectly
        # collapsed into ``decide``.
        ("prioritize", ("what should i do next", "what should i work on", "prioritize", "priority", "focus on first")),
        ("plan", ("make a plan", "plan how", "roadmap", "steps to", "how should i prepare", "get this ready")),
        ("advise", ("what should i do to", "what should i do about", "what should i do for")),
        ("decide", ("should i", "which should", "which one", "help me decide", "better option")),
        ("create", (
            "write me", "draft", "generate", "create a", "build a", "give me code",
            "write code", "show code", "show me code", "write python",
            "write javascript", "write typescript", "write sql", "code example",
        )),
        ("summarize", ("summarize", "summary", "recap", "tl;dr")),
        ("explain", ("explain", "teach me", "what does", "how does", "what is ", "what are ")),
        ("advise", ("what should", "how should", "how can i", "recommend", "best way", "what would you do")),
        ("analyze", ("analyze", "analyse", "review", "assess", "evaluate", "what risks")),
    )
    for task_type, markers in rules:
        if _has(text, markers):
            return task_type, 0.88
    if text.endswith("?"):
        return "factual", 0.62
    return "advise", 0.50


def _extract_inline_expression(query: str) -> str | None:
    text = str(query or "")
    # Only accept arithmetic that is literally present in the user's text. A
    # standalone number/percentage is not an expression: natural-language math
    # such as "20% of 500" must go through request understanding so we do not
    # silently calculate the wrong fragment.
    candidates = re.findall(
        r"(?<![A-Za-z_])(?:\d[\d,]*(?:\.\d+)?|[()])(?:[\d\s,.()+\-*/^%]*)(?:\d(?:[\d,]*(?:\.\d+)?)|[)])(?![A-Za-z_])",
        text,
    )
    for raw in sorted(candidates, key=len, reverse=True):
        expression = raw.replace(",", "").strip()
        expression = expression.replace("^", "**")
        # Require an actual binary arithmetic operator. Percent signs by
        # themselves are intentionally excluded because "20% of 500" is
        # natural language, while modulo must be explicitly between operands.
        has_binary = bool(re.search(r"\d\s*(?:\*\*|[+\-*/]|%\s*\d)", expression))
        if not has_binary:
            continue
        if len(expression) > MAX_CALCULATOR_EXPRESSION_CHARACTERS:
            continue
        return expression
    return None


def deterministic_request_profile(
    *,
    query: str,
    route_intent: str | None,
    selected_context_type: str | None,
) -> RequestProfile:
    text = f" {_normalized(query)} "
    task_type, _confidence = _heuristic_task_type(text)
    math_needed = _looks_like_math(text)
    if math_needed and task_type in {"factual", "explain", "advise"}:
        task_type = "calculate"
    code_needed = _looks_like_code(text)
    web_needed = _looks_like_web(text)
    mutation = _looks_like_mutation(text)

    if selected_context_type in {"document", "collection", "module", "lecture"}:
        # An explicit knowledge chip is the factual scope. A coincidental project
        # route hint must not pull unrelated project state into that answer.
        needs_workspace = False
    else:
        needs_workspace = bool(
            selected_context_type == "project"
            or str(route_intent or "").startswith("project_")
            or route_intent in {"portfolio_focus", "portfolio_review", "today_focus", "task_status", "deadline_review"}
        )
    needs_rag = selected_context_type in {"document", "collection", "module", "lecture"} or _has(text, (
        "according to the document", "according to this document", "based on the document", "project documents",
        "linked documents", "pdf", "in the file", "from the file",
    ))
    if selected_context_type in {"document", "collection", "module", "lecture"}:
        knowledge_scope = "documents"
    elif needs_workspace:
        knowledge_scope = "workspace_plus_general"
    else:
        knowledge_scope = "general"

    complexity = "reasoning"
    if task_type == "factual" and not (web_needed or math_needed or code_needed):
        complexity = "simple"
    if task_type in {"plan", "execute"} and _has(text, ("entire", "everything", "end to end", "end-to-end", "full plan", "from start to finish", "all the steps")):
        complexity = "multi_step"

    action_mode = "mutation_requested" if mutation else ("recommendation" if task_type in {"advise", "decide", "prioritize", "plan", "troubleshoot"} else "read_only")
    if mutation:
        task_type = "execute"
        complexity = "multi_step"

    return RequestProfile(
        task_type=task_type,
        complexity=complexity,
        knowledge_scope=knowledge_scope,
        needs_workspace=needs_workspace,
        needs_rag=needs_rag,
        needs_web=web_needed,
        needs_calculator=math_needed,
        needs_code=code_needed,
        action_mode=action_mode,
        web_query=str(query or "").strip()[:MAX_PUBLIC_WEB_QUERY_CHARACTERS] if web_needed else None,
        calculator_expression=_extract_inline_expression(query) if math_needed else None,
        source="deterministic",
    )


def _strip_json_fences(raw: str) -> str:
    cleaned = str(raw or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _parse_bool(value: Any, fallback: bool) -> bool:
    return value if isinstance(value, bool) else fallback


def _parse_ai_profile(raw: str, fallback: RequestProfile) -> RequestProfile:
    try:
        parsed = json.loads(_strip_json_fences(raw))
    except (TypeError, json.JSONDecodeError) as error:
        raise RequestUnderstandingError("Request understanding returned invalid JSON.") from error
    if not isinstance(parsed, dict):
        raise RequestUnderstandingError("Request understanding returned an invalid profile.")

    task_type = str(parsed.get("task_type") or fallback.task_type).strip().lower()
    complexity = str(parsed.get("complexity") or fallback.complexity).strip().lower()
    knowledge_scope = str(parsed.get("knowledge_scope") or fallback.knowledge_scope).strip().lower()
    action_mode = str(parsed.get("action_mode") or fallback.action_mode).strip().lower()
    if task_type not in TASK_TYPES:
        task_type = fallback.task_type
    if complexity not in COMPLEXITIES:
        complexity = fallback.complexity
    if knowledge_scope not in KNOWLEDGE_SCOPES:
        knowledge_scope = fallback.knowledge_scope
    if action_mode not in ACTION_MODES:
        action_mode = fallback.action_mode

    web_query = " ".join(str(parsed.get("web_query") or "").split()).strip() or fallback.web_query
    if web_query:
        web_query = web_query[:MAX_PUBLIC_WEB_QUERY_CHARACTERS]
    calculator_expression = " ".join(str(parsed.get("calculator_expression") or "").split()).strip() or fallback.calculator_expression
    if calculator_expression:
        calculator_expression = calculator_expression[:MAX_CALCULATOR_EXPRESSION_CHARACTERS]

    # Deterministic safety/capability signals are a floor, not a suggestion. The
    # classifier may add capabilities, but it cannot downgrade an explicit
    # mutation request, selected workspace/document scope, or an explicitly
    # requested web/math/code capability.
    needs_workspace = fallback.needs_workspace or _parse_bool(parsed.get("needs_workspace"), False)
    needs_rag = fallback.needs_rag or _parse_bool(parsed.get("needs_rag"), False)
    needs_web = fallback.needs_web or _parse_bool(parsed.get("needs_web"), False)
    needs_calculator = fallback.needs_calculator or _parse_bool(parsed.get("needs_calculator"), False)
    needs_code = fallback.needs_code or _parse_bool(parsed.get("needs_code"), False)

    if fallback.needs_rag and knowledge_scope not in {"documents", "mixed"}:
        knowledge_scope = "documents" if not fallback.needs_workspace else "mixed"
    elif fallback.needs_workspace and knowledge_scope not in {"workspace", "workspace_plus_general", "mixed"}:
        knowledge_scope = fallback.knowledge_scope

    if fallback.action_mode == "mutation_requested":
        action_mode = "mutation_requested"
        task_type = "execute"
        complexity = "multi_step"
    elif action_mode == "mutation_requested":
        # A classifier cannot invent write intent that deterministic request
        # understanding did not see. Mutations are recognized from the user's
        # explicit words and remain behind I9. Also discard the classifier's
        # execute/multi-step shape so a false write classification cannot trigger
        # an unnecessary agent plan.
        action_mode = fallback.action_mode
        if task_type == "execute":
            task_type = fallback.task_type
            complexity = fallback.complexity

    return RequestProfile(
        task_type=task_type,
        complexity=complexity,
        knowledge_scope=knowledge_scope,
        needs_workspace=needs_workspace,
        needs_rag=needs_rag,
        needs_web=needs_web,
        needs_calculator=needs_calculator,
        needs_code=needs_code,
        action_mode=action_mode,
        web_query=web_query if needs_web else None,
        calculator_expression=calculator_expression if needs_calculator else None,
        source="ai",
    )


def _should_use_ai_profile(query: str, fallback: RequestProfile, *, route_intent: str | None) -> bool:
    # Existing deterministic factual/RAG routes should not pay a classifier call.
    if route_intent in {
        "memory_query", "memory_candidate", "today_focus", "task_status", "deadline_review",
        "document_review", "workspace_gaps", "study_next", "project_question", "recent_activity",
        "context_connections", "portfolio_focus", "portfolio_review", "project_focus",
    }:
        return False
    text = _normalized(query)
    # Natural-language math still needs one cheap translation step when there is
    # no literal safe expression. Do this before speech-act confidence checks: a
    # phrase like "what is 20% of 500?" is linguistically clear but not yet a
    # deterministic calculator expression.
    if fallback.needs_calculator and not fallback.calculator_expression:
        return True

    _task_type, confidence = _heuristic_task_type(f" {text} ")
    # Clear speech acts are already domain-agnostic and should not spend a
    # classifier call. The cheap model is reserved for genuinely ambiguous text.
    if confidence >= 0.80:
        return False

    # Explicit capability requests already have a high-signal deterministic
    # profile. Natural-language math is the exception: if no safe expression was
    # extracted, use the CHEAP classifier to translate it into one.
    calculator_is_explicit = bool(fallback.needs_calculator and fallback.calculator_expression)
    explicit = fallback.needs_web or calculator_is_explicit or _has(text, (
        "write code", "show code", "show me code", "give me code", "debug this code",
        "compare", "summarize", "explain", "research",
    ))
    return not explicit


def understand_request(
    *,
    query: str,
    route_intent: str | None,
    selected_context_type: str | None = None,
    selected_context_label: str | None = None,
    allow_ai: bool = True,
) -> RequestProfile:
    """Return a provider-independent request/capability profile.

    The classifier receives no database rows, document text, credentials or hidden
    configuration.  It sees only the authenticated user's request plus coarse
    context type/label. Failure falls back to deterministic universal rules.
    """

    fallback = deterministic_request_profile(
        query=query,
        route_intent=route_intent,
        selected_context_type=selected_context_type,
    )
    if not allow_ai or not _should_use_ai_profile(query, fallback, route_intent=route_intent):
        return fallback

    try:
        config = get_ai_configuration()
    except AIServiceError:
        return fallback

    context_note = (
        f"Selected context: {selected_context_type or 'none'}"
        + (f" ({selected_context_label})" if selected_context_label else "")
    )
    prompt = f"""
You are the tiny request-understanding layer for Ask LifeOS.
Classify HOW the request should be solved, not its subject/domain.
Do not answer the request. Do not invent LifeOS facts.

Allowed task_type values: {', '.join(sorted(TASK_TYPES))}
Allowed complexity values: {', '.join(sorted(COMPLEXITIES))}
Allowed knowledge_scope values: {', '.join(sorted(KNOWLEDGE_SCOPES))}
Allowed action_mode values: {', '.join(sorted(ACTION_MODES))}

Capability rules:
- needs_web=true only when fresh/current/public external information would materially improve correctness, or the user explicitly asks to search/browse/research online.
- web_query must be a concise PUBLIC research query. Do not include secrets, credentials, private database values, or hidden LifeOS context. Do not add a selected project/document name unless the user explicitly typed that name as something to research publicly.
- needs_calculator=true when exact arithmetic/math should be computed. If possible return calculator_expression using only numbers, + - * / // % **, parentheses, pi/e, and standard functions such as sqrt/log/round.
- needs_code=true when code, pseudocode, a query, or a concrete implementation example would materially improve the answer. This means GENERATE code, never execute it.
- action_mode=mutation_requested only when the user is actually asking LifeOS to change/save/create/delete/schedule workspace state. Advice about a possible change is recommendation.
- complexity=multi_step only for goals requiring several dependent checks/actions; do not turn an ordinary advice question into an agent run.
- selected context defines factual scope, not the limits of general reasoning.

Return JSON only:
{{
  "task_type": "advise",
  "complexity": "reasoning",
  "knowledge_scope": "workspace_plus_general",
  "needs_workspace": true,
  "needs_rag": false,
  "needs_web": false,
  "needs_calculator": false,
  "needs_code": false,
  "action_mode": "recommendation",
  "web_query": null,
  "calculator_expression": null
}}

ROUTE HINT: {route_intent or 'general_conversation'}
{context_note}
USER REQUEST:
{str(query or '').strip()}
""".strip()
    try:
        raw = route_ai_text(
            provider=config["provider"],
            api_key=config["api_key"],
            model=config["model"],
            feature="ask_lifeos_request_understanding",
            prompt=prompt,
            json_mode=True,
            empty_message="LifeOS request understanding returned an empty result.",
        )
        profile = _parse_ai_profile(raw, fallback)
    except (AIProviderRouterError, RequestUnderstandingError):
        return fallback

    # Ownership/context requirements are deterministic and cannot be downgraded
    # by the classifier.
    if fallback.needs_workspace and not profile.needs_workspace:
        profile = replace(profile, needs_workspace=True)
    if selected_context_type in {"document", "collection", "module", "lecture"} and not profile.needs_rag:
        profile = replace(profile, needs_rag=True)
    if profile.action_mode == "mutation_requested" and profile.complexity != "multi_step":
        profile = replace(profile, complexity="multi_step", task_type="execute")
    return profile
