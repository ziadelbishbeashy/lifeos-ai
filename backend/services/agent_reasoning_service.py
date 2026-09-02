"""I19 reasoning over bounded read-only agent observations.

The provider receives only compact observations/evidence produced by approved
LifeOS tools. It cannot call tools itself. Every returned claim/recommendation
must cite evidence IDs that exist in the server-built catalog; verification is
performed deterministically in code, avoiding a second verifier provider call.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from ai.provider_router import AIProviderRouterError, generate_text as route_ai_text
from services.ai_service import AIServiceError, get_ai_configuration
from services.document_security_service import DOCUMENT_SECURITY_PROMPT_RULES, render_untrusted_prompt_data

MAX_AGENT_ANSWER_CHARACTERS = 5_000
MAX_AGENT_REASONING_ITEMS = 10


class AgentReasoningError(RuntimeError):
    pass


class AgentReasoningProviderError(AgentReasoningError):
    pass


class AgentReasoningValidationError(AgentReasoningError):
    pass


@dataclass(frozen=True)
class AgentReasoningItem:
    text: str
    evidence_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "evidence_ids": list(self.evidence_ids)}


@dataclass(frozen=True)
class AgentReasoningResult:
    answer: str
    claims: tuple[AgentReasoningItem, ...]
    recommendations: tuple[AgentReasoningItem, ...]
    provider: str
    model: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "claims": [item.to_dict() for item in self.claims],
            "recommendations": [item.to_dict() for item in self.recommendations],
            "provider": self.provider,
            "model": self.model,
        }


def _strip_fence(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _clean_text(value: Any, *, field: str, limit: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        raise AgentReasoningValidationError(f"Agent reasoning field {field} is empty.")
    if len(text) > limit:
        raise AgentReasoningValidationError(f"Agent reasoning field {field} is too long.")
    return text


def _items(value: Any, *, field: str, valid_evidence_ids: set[str]) -> tuple[AgentReasoningItem, ...]:
    if value in (None, []):
        return ()
    if not isinstance(value, list) or len(value) > MAX_AGENT_REASONING_ITEMS:
        raise AgentReasoningValidationError(f"{field} must be a bounded list.")
    result: list[AgentReasoningItem] = []
    for index, raw in enumerate(value, start=1):
        if not isinstance(raw, dict):
            raise AgentReasoningValidationError(f"{field}[{index}] must be an object.")
        text = _clean_text(raw.get("text"), field=f"{field}[{index}].text", limit=1_600)
        raw_ids = raw.get("evidence_ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise AgentReasoningValidationError(f"{field}[{index}] must cite evidence.")
        ids: list[str] = []
        for raw_id in raw_ids[:6]:
            evidence_id = str(raw_id or "").strip()
            if evidence_id not in valid_evidence_ids:
                raise AgentReasoningValidationError(
                    f"{field}[{index}] cited evidence that LifeOS did not provide."
                )
            if evidence_id not in ids:
                ids.append(evidence_id)
        if not ids:
            raise AgentReasoningValidationError(f"{field}[{index}] has no valid evidence.")
        result.append(AgentReasoningItem(text=text, evidence_ids=tuple(ids)))
    return tuple(result)


def reason_over_agent_observations(
    *,
    goal: str,
    scope: dict[str, Any],
    evidence_catalog: list[dict[str, Any]],
) -> AgentReasoningResult:
    if not evidence_catalog:
        raise AgentReasoningValidationError("The agent has no trusted observations to reason over.")

    valid_ids = {str(item.get("id")) for item in evidence_catalog if item.get("id")}
    try:
        config = get_ai_configuration()
    except AIServiceError as error:
        raise AgentReasoningProviderError(str(error)) from error
    evidence_json = json.dumps(evidence_catalog, ensure_ascii=False)
    prompt = f"""
You are the reasoning component inside the constrained LifeOS Agent Runtime.

Your job is to help with the user's GOAL using ONLY the LIFEOS EVIDENCE below.
You do not have tools, database access, SQL access, code execution, or permission
for workspace mutations. Tool selection and ownership checks have already been
performed by LifeOS code.

Return exactly one JSON object with this shape:
{{
  "answer": "concise useful answer to the goal",
  "claims": [{{"text": "factual or inferred claim", "evidence_ids": ["evidence-id"]}}],
  "recommendations": [{{"text": "recommended next step", "evidence_ids": ["evidence-id"]}}]
}}

Rules:
- Every claim and recommendation must cite one or more exact evidence IDs below.
- Never invent IDs, facts, deadlines, tasks, files, project state, or actions.
- If evidence is incomplete, explicitly say what is missing.
- Synthesize the evidence into a decision-oriented answer; do not dump or enumerate every evidence item.
- Lead with the most important blocker or conclusion, explain why it matters, then state the few next steps that best move the goal forward.
- Prefer at most three recommendations. Avoid repeating the same risk in different wording.
- Recommendations are advice only. Never claim a workspace change happened.
- Important actions still require the separate I9 confirmation boundary.
- Keep the answer practical and under {MAX_AGENT_ANSWER_CHARACTERS} characters.

{DOCUMENT_SECURITY_PROMPT_RULES}

GOAL:
{render_untrusted_prompt_data("USER_GOAL", goal)}

SELECTED SCOPE:
{render_untrusted_prompt_data("LIFEOS_SCOPE", json.dumps(scope, ensure_ascii=False))}

LIFEOS EVIDENCE:
{render_untrusted_prompt_data("LIFEOS_EVIDENCE", evidence_json)}
"""
    try:
        raw = route_ai_text(
            provider=config["provider"],
            api_key=config["api_key"],
            model=config["model"],
            prompt=prompt,
            empty_message="The AI provider returned an empty agent answer.",
        )
    except (AIServiceError, AIProviderRouterError) as error:
        raise AgentReasoningProviderError(str(error)) from error

    try:
        parsed = json.loads(_strip_fence(raw))
    except (TypeError, json.JSONDecodeError) as error:
        raise AgentReasoningValidationError("The agent reasoner returned invalid structured output.") from error
    if not isinstance(parsed, dict):
        raise AgentReasoningValidationError("The agent reasoner must return one JSON object.")

    answer = _clean_text(parsed.get("answer"), field="answer", limit=MAX_AGENT_ANSWER_CHARACTERS)
    claims = _items(parsed.get("claims"), field="claims", valid_evidence_ids=valid_ids)
    recommendations = _items(
        parsed.get("recommendations"), field="recommendations", valid_evidence_ids=valid_ids
    )
    if not claims and not recommendations:
        raise AgentReasoningValidationError("The agent answer did not cite any trusted evidence.")

    return AgentReasoningResult(
        answer=answer,
        claims=claims,
        recommendations=recommendations,
        provider=config["provider"],
        model=config["model"],
    )
