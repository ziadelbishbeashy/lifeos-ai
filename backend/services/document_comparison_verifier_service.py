"""Step 13D — fail-closed verification for two-document comparisons.

The comparison generator from Step 13C is intentionally untrusted. This module
validates source identities/category requirements and asks a second verifier
pass whether each proposed material difference is actually supported by the
exact trusted A/B evidence supplied by Step 13B.

Only findings accepted here may be persisted as Completed comparison results.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from ai.provider_router import (
    AIProviderRouterError,
    generate_text as route_ai_text,
)
from services.ai_service import (
    AIServiceError,
    get_ai_configuration,
)
from services.document_security_service import (
    DOCUMENT_SECURITY_PROMPT_RULES,
    log_untrusted_content_assessment,
    render_untrusted_prompt_data,
)
from services.document_comparison_candidate_service import (
    ComparisonEvidence,
    DocumentComparisonCandidateBundle,
)


MAX_VERIFIER_FINDINGS = 40
MAX_VERIFIER_CONTEXT_CHARACTERS = 30_000
MAX_VERIFIER_REASON_CHARACTERS = 800


class DocumentComparisonVerificationError(RuntimeError):
    """Base exception for Step 13D verification failures."""


class DocumentComparisonVerificationValidationError(
    DocumentComparisonVerificationError
):
    """Raised when a generated comparison cannot be safely verified."""


class DocumentComparisonVerificationProviderError(
    DocumentComparisonVerificationError
):
    """Raised when the configured verification provider fails."""


@dataclass(frozen=True)
class VerifiedComparisonResult:
    """Comparison content that passed deterministic + AI evidence checks."""

    summary: str
    findings: list[dict[str, Any]]
    verifier_provider: str
    verifier_model: str
    rejected_findings: int


def verify_document_comparison_draft(
    *,
    bundle: DocumentComparisonCandidateBundle,
    comparison: dict[str, Any],
) -> VerifiedComparisonResult:
    """Verify the generated comparison and copy sources from trusted evidence."""

    raw_findings = comparison.get(
        "findings",
        [],
    )

    if not isinstance(
        raw_findings,
        list,
    ):
        raise DocumentComparisonVerificationValidationError(
            "The generated comparison findings are invalid."
        )

    raw_findings = raw_findings[
        :MAX_VERIFIER_FINDINGS
    ]

    if not raw_findings:
        return VerifiedComparisonResult(
            summary=_build_safe_summary(
                findings=[],
            ),
            findings=[],
            verifier_provider="lifeos",
            verifier_model="deterministic-no-findings",
            rejected_findings=0,
        )

    evidence_by_id = bundle.evidence_by_id

    eligible: list[
        tuple[int, dict[str, Any], list[ComparisonEvidence], list[ComparisonEvidence]]
    ] = []

    deterministic_rejected = 0

    for finding_index, finding in enumerate(
        raw_findings,
        start=1,
    ):
        prepared = _prepare_finding_for_verification(
            finding=finding,
            finding_index=finding_index,
            bundle=bundle,
            evidence_by_id=evidence_by_id,
        )

        if prepared is None:
            deterministic_rejected += 1
            continue

        eligible.append(prepared)

    if not eligible:
        raise DocumentComparisonVerificationValidationError(
            "LifeOS could not verify any generated document differences "
            "against the trusted source evidence."
        )

    verifier_context = _build_verifier_context(
        eligible=eligible,
        bundle=bundle,
    )

    if (
        len(verifier_context)
        > MAX_VERIFIER_CONTEXT_CHARACTERS
    ):
        raise DocumentComparisonVerificationValidationError(
            "The comparison verification context is too large."
        )

    try:
        config = get_ai_configuration()

    except AIServiceError as error:
        raise DocumentComparisonVerificationProviderError(
            str(error)
        ) from error

    log_untrusted_content_assessment(
        verifier_context,
        source_kind="document_comparison_verifier_context",
    )

    prompt = _build_verifier_prompt(
        verifier_context=verifier_context,
    )

    try:
        raw_response = route_ai_text(
            provider=config["provider"],
            api_key=config["api_key"],
            model=config["model"],
            prompt=prompt,
            empty_message=(
                "The AI provider returned an empty comparison "
                "verification result."
            ),
        )

    except AIProviderRouterError as error:
        raise DocumentComparisonVerificationProviderError(
            str(error)
        ) from error

    decisions = _parse_verifier_response(
        raw_response,
        valid_indexes={
            finding_index
            for (
                finding_index,
                _finding,
                _sources_a,
                _sources_b,
            ) in eligible
        },
    )

    verified_findings: list[
        dict[str, Any]
    ] = []

    rejected_by_verifier = 0

    for (
        finding_index,
        finding,
        sources_a,
        sources_b,
    ) in eligible:
        decision = decisions.get(
            finding_index
        )

        if (
            decision is None
            or decision["supported"] is not True
            or decision["confidence"] != "high"
        ):
            rejected_by_verifier += 1
            continue

        verified_findings.append(
            _copy_verified_finding(
                finding=finding,
                sources_a=sources_a,
                sources_b=sources_b,
            )
        )

    if not verified_findings:
        raise DocumentComparisonVerificationValidationError(
            "The generated differences were not supported strongly enough "
            "by the selected document evidence."
        )

    return VerifiedComparisonResult(
        summary=_build_safe_summary(
            verified_findings
        ),
        findings=verified_findings,
        verifier_provider=str(
            config["provider"]
        )[:30],
        verifier_model=str(
            config["model"]
        )[:100],
        rejected_findings=(
            deterministic_rejected
            + rejected_by_verifier
        ),
    )


def _prepare_finding_for_verification(
    *,
    finding: Any,
    finding_index: int,
    bundle: DocumentComparisonCandidateBundle,
    evidence_by_id: dict[str, ComparisonEvidence],
) -> tuple[
    int,
    dict[str, Any],
    list[ComparisonEvidence],
    list[ComparisonEvidence],
] | None:
    if not isinstance(
        finding,
        dict,
    ):
        return None

    category = str(
        finding.get("category")
        or ""
    ).strip()

    if category not in {
        "changed",
        "added",
        "removed",
        "potential_conflict",
    }:
        return None

    raw_a = finding.get(
        "document_a"
    )

    raw_b = finding.get(
        "document_b"
    )

    side_a = (
        raw_a
        if isinstance(
            raw_a,
            dict,
        )
        else {}
    )

    side_b = (
        raw_b
        if isinstance(
            raw_b,
            dict,
        )
        else {}
    )

    sources_a = _resolve_sources(
        source_ids=side_a.get(
            "source_ids",
            [],
        ),
        expected_side="A",
        evidence_by_id=evidence_by_id,
    )

    sources_b = _resolve_sources(
        source_ids=side_b.get(
            "source_ids",
            [],
        ),
        expected_side="B",
        evidence_by_id=evidence_by_id,
    )

    if category in {
        "changed",
        "potential_conflict",
    }:
        if not sources_a or not sources_b:
            return None

    elif category == "added":
        if not sources_b:
            return None

        # "Added" contains an absence claim about A. That is unsafe when A
        # was only sampled through chunks or its candidate set was truncated.
        if not _coverage_supports_absence_claim(
            bundle.coverage_a
        ):
            return None

    elif category == "removed":
        if not sources_a:
            return None

        # "Removed" contains an absence claim about B.
        if not _coverage_supports_absence_claim(
            bundle.coverage_b
        ):
            return None

    return (
        finding_index,
        finding,
        sources_a,
        sources_b,
    )


def _coverage_supports_absence_claim(
    coverage,
) -> bool:
    return (
        coverage.analysis_status == "Current"
        and coverage.structured_evidence_count > 0
        and coverage.truncated is False
    )


def _resolve_sources(
    *,
    source_ids: Any,
    expected_side: str,
    evidence_by_id: dict[str, ComparisonEvidence],
) -> list[ComparisonEvidence]:
    if not isinstance(
        source_ids,
        list,
    ):
        return []

    resolved: list[
        ComparisonEvidence
    ] = []

    seen: set[str] = set()

    for raw_source_id in source_ids:
        source_id = str(
            raw_source_id
            or ""
        ).strip().upper()

        if (
            not source_id.startswith(
                expected_side
            )
            or source_id in seen
        ):
            continue

        evidence = evidence_by_id.get(
            source_id
        )

        if (
            evidence is None
            or evidence.side != expected_side
        ):
            continue

        seen.add(source_id)
        resolved.append(evidence)

    return resolved


def _build_verifier_context(
    *,
    eligible: list[
        tuple[
            int,
            dict[str, Any],
            list[ComparisonEvidence],
            list[ComparisonEvidence],
        ]
    ],
    bundle: DocumentComparisonCandidateBundle,
) -> str:
    blocks = [
        (
            "DOCUMENT A\n"
            f"Filename: {bundle.document_a.filename}\n"
            f"Coverage: {bundle.coverage_a.mode}\n"
            f"Analysis status: {bundle.coverage_a.analysis_status}\n"
            f"Truncated: {'yes' if bundle.coverage_a.truncated else 'no'}"
        ),
        (
            "DOCUMENT B\n"
            f"Filename: {bundle.document_b.filename}\n"
            f"Coverage: {bundle.coverage_b.mode}\n"
            f"Analysis status: {bundle.coverage_b.analysis_status}\n"
            f"Truncated: {'yes' if bundle.coverage_b.truncated else 'no'}"
        ),
    ]

    for (
        finding_index,
        finding,
        sources_a,
        sources_b,
    ) in eligible:
        block = [
            f"FINDING {finding_index}",
            f"Category: {finding.get('category', '')}",
            f"Topic: {finding.get('topic', '')}",
            f"Explanation: {finding.get('explanation', '')}",
            (
                "Document A statement: "
                f"{_side_statement(finding, 'document_a')}"
            ),
            (
                "Document B statement: "
                f"{_side_statement(finding, 'document_b')}"
            ),
            "TRUSTED CITED SOURCES:",
        ]

        for source in [
            *sources_a,
            *sources_b,
        ]:
            location = []

            if source.page is not None:
                location.append(
                    f"Page {source.page}"
                )

            if source.section:
                location.append(
                    source.section
                )

            block.extend(
                [
                    (
                        f"[{source.source_id} | {source.filename} | "
                        f"{' | '.join(location) or 'Location unavailable'}]"
                    ),
                    (
                        f"Source evidence: "
                        f"{source.evidence or source.statement}"
                    ),
                ]
            )

        blocks.append(
            "\n".join(
                block
            )
        )

    return "\n\n".join(
        blocks
    )


def _build_verifier_prompt(
    *,
    verifier_context: str,
) -> str:
    return f"""
You are the evidence verifier for LifeOS two-document comparison.

You do NOT generate new differences.
You only decide whether each proposed finding is directly supported by its
trusted cited evidence.

{DOCUMENT_SECURITY_PROMPT_RULES}
SECURITY AND GROUNDING RULES:
1. Use only the trusted cited sources attached to each finding.
2. Do not rely on outside knowledge.
3. "Changed" requires evidence from both A and B showing the same underlying
   topic with a material difference.
4. "Potential conflict" requires evidence from both A and B showing genuinely
   incompatible claims. Different values alone are not automatically a conflict.
5. "Added" means the B item is supported and its absence from A is sufficiently
   justified by the coverage information.
6. "Removed" means the A item is supported and its absence from B is sufficiently
   justified by the coverage information.
7. Rewording with the same meaning is NOT a material change.
8. Never infer that B is newer, current, authoritative, or supersedes A.
9. Mark supported=true ONLY with HIGH confidence.
10. Return one decision for every FINDING number supplied.
11. Do not return source IDs. LifeOS already owns and validates them.
12. Return JSON only, without Markdown fences.

RETURN:
{{
  "decisions": [
    {{
      "finding_index": 1,
      "supported": true,
      "confidence": "high",
      "reason": "Brief reason"
    }}
  ]
}}

{render_untrusted_prompt_data("COMPARISON FINDINGS AND TRUSTED EVIDENCE", verifier_context)}
"""


def _parse_verifier_response(
    raw_response: str,
    *,
    valid_indexes: set[int],
) -> dict[int, dict[str, Any]]:
    cleaned = str(
        raw_response
        or ""
    ).strip()

    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
    )

    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")

    if (
        first_brace == -1
        or last_brace == -1
    ):
        raise DocumentComparisonVerificationValidationError(
            "The comparison verifier returned invalid data."
        )

    try:
        parsed = json.loads(
            cleaned[
                first_brace:last_brace + 1
            ]
        )

    except json.JSONDecodeError as error:
        raise DocumentComparisonVerificationValidationError(
            "The comparison verifier returned invalid JSON."
        ) from error

    raw_decisions = (
        parsed.get("decisions")
        if isinstance(
            parsed,
            dict,
        )
        else None
    )

    if not isinstance(
        raw_decisions,
        list,
    ):
        raise DocumentComparisonVerificationValidationError(
            "The comparison verifier did not return decisions."
        )

    decisions: dict[
        int,
        dict[str, Any]
    ] = {}

    for raw_decision in raw_decisions:
        if not isinstance(
            raw_decision,
            dict,
        ):
            continue

        try:
            finding_index = int(
                raw_decision.get(
                    "finding_index"
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if (
            finding_index not in valid_indexes
            or finding_index in decisions
        ):
            continue

        supported = (
            raw_decision.get(
                "supported"
            )
            is True
        )

        confidence = str(
            raw_decision.get(
                "confidence"
                )
            or ""
        ).strip().casefold()

        if confidence not in {
            "low",
            "medium",
            "high",
        }:
            confidence = "low"

        reason = " ".join(
            str(
                raw_decision.get(
                    "reason"
                )
                or ""
            ).split()
        )[:MAX_VERIFIER_REASON_CHARACTERS]

        decisions[
            finding_index
        ] = {
            "supported": supported,
            "confidence": confidence,
            "reason": reason,
        }

    return decisions


def _copy_verified_finding(
    *,
    finding: dict[str, Any],
    sources_a: list[ComparisonEvidence],
    sources_b: list[ComparisonEvidence],
) -> dict[str, Any]:
    return {
        "category": finding["category"],
        "topic": str(
            finding.get(
                "topic"
            )
            or ""
        ).strip(),
        "explanation": str(
            finding.get(
                "explanation"
            )
            or ""
        ).strip(),
        "confidence": str(
            finding.get(
                "confidence"
            )
            or "Medium"
        ).strip(),
        "document_a": {
            "statement": _side_statement(
                finding,
                "document_a",
            ),
            "sources": [
                _trusted_source_snapshot(
                    source
                )
                for source in sources_a
            ],
        },
        "document_b": {
            "statement": _side_statement(
                finding,
                "document_b",
            ),
            "sources": [
                _trusted_source_snapshot(
                    source
                )
                for source in sources_b
            ],
        },
    }


def _trusted_source_snapshot(
    source: ComparisonEvidence,
) -> dict[str, Any]:
    return {
        "document_id": source.document_id,
        "filename": source.filename,
        "page": source.page,
        "section": source.section or None,
        "evidence": source.evidence or source.statement,
        # Backend provenance only. Templates never surface these fields.
        "chunk_id": source.chunk_id,
        "chunk_index": source.chunk_index,
        "visibility": "owner",
    }


def _side_statement(
    finding: dict[str, Any],
    side: str,
) -> str:
    raw_side = finding.get(
        side
    )

    if not isinstance(
        raw_side,
        dict,
    ):
        return ""

    return " ".join(
        str(
            raw_side.get(
                "statement"
            )
            or ""
        ).split()
    )[:1_200]


def _build_safe_summary(
    findings: list[dict[str, Any]],
) -> str:
    if not findings:
        return (
            "No material differences were verified in the available "
            "comparison evidence."
        )

    counts = {
        "changed": 0,
        "added": 0,
        "removed": 0,
        "potential_conflict": 0,
    }

    for finding in findings:
        category = finding.get(
            "category"
        )

        if category in counts:
            counts[
                category
            ] += 1

    parts = []

    labels = (
        ("changed", "changed"),
        ("added", "added"),
        ("removed", "removed"),
        (
            "potential_conflict",
            "potential conflict",
        ),
    )

    for key, label in labels:
        count = counts[key]

        if count:
            parts.append(
                f"{count} {label}"
            )

    return (
        f"LifeOS verified {len(findings)} material difference"
        f"{'' if len(findings) == 1 else 's'}"
        + (
            f": {', '.join(parts)}."
            if parts
            else "."
        )
    )
