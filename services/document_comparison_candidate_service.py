"""Step 13B — document comparison evidence/candidate builder.

The candidate builder prepares a bounded, ownership-safe evidence registry for
two already validated LifeOS documents.

It prefers CURRENT structured Document Brain findings, preserving their
page/section/evidence provenance, and supplements them with page-aware document
chunks. If the structured analysis is stale or missing, chunk evidence becomes
the safe fallback.

The service does not ask an AI model to compare documents and does not persist
a comparison result.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any, Iterable

from models import (
    Document,
    DocumentAIAnalysis,
    DocumentChunk,
)
from services.document_analysis_service import (
    DOCUMENT_ANALYSIS_SCHEMA_VERSION,
)
from services.document_chunk_service import (
    DocumentChunkError,
    DocumentChunkNotFoundError,
    DocumentChunkNotReadyError,
    ensure_owned_document_chunks,
)
from services.document_comparison_service import (
    require_owned_document_pair,
)


MAX_STRUCTURED_EVIDENCE_PER_SIDE = 18
MAX_SUPPLEMENTAL_CHUNKS_WITH_ANALYSIS = 6
MAX_FALLBACK_CHUNKS_WITHOUT_ANALYSIS = 16
MAX_TOTAL_EVIDENCE_PER_SIDE = 24
MAX_COMPARISON_EVIDENCE_CONTEXT_CHARACTERS = 30_000

PAGE_MARKER_PATTERN = re.compile(
    r"--- Page\s+\d+\s+---",
    flags=re.IGNORECASE,
)


class DocumentComparisonCandidateError(RuntimeError):
    """Raised when comparison evidence cannot be prepared."""


class DocumentComparisonCandidateNotReadyError(
    DocumentComparisonCandidateError
):
    """Raised when neither selected document has usable comparison evidence."""


@dataclass(frozen=True)
class ComparisonEvidence:
    """One trusted source unit offered to semantic comparison."""

    source_id: str
    side: str
    document_id: int
    filename: str
    kind: str
    topic: str
    statement: str
    detail: str
    page: int | None
    section: str
    evidence: str
    origin: str
    chunk_id: int | None = None
    chunk_index: int | None = None

    @property
    def comparison_text(self) -> str:
        """Compact meaning used by alignment and the comparison model."""

        parts = [
            self.topic,
            self.statement,
            self.detail,
            self.evidence,
        ]

        seen: set[str] = set()
        cleaned: list[str] = []

        for part in parts:
            value = _compact_text(
                part,
                1_800,
            )

            key = value.casefold()

            if not value or key in seen:
                continue

            seen.add(key)
            cleaned.append(value)

        return "\n".join(cleaned)

    def source(self) -> dict[str, Any]:
        """Backend provenance. Technical chunk metadata stays out of the UI."""

        return {
            "source_id": self.source_id,
            "side": self.side,
            "document_id": self.document_id,
            "filename": self.filename,
            "kind": self.kind,
            "page": self.page,
            "section": self.section or None,
            "evidence": self.evidence,
            "origin": self.origin,
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "visibility": "owner",
        }


@dataclass(frozen=True)
class DocumentCandidateCoverage:
    """How one document contributed evidence to the comparison."""

    document_id: int
    filename: str
    analysis_status: str
    analysis_id: int | None
    structured_evidence_count: int
    chunk_evidence_count: int
    mode: str
    truncated: bool


@dataclass(frozen=True)
class DocumentComparisonCandidateBundle:
    """Ordered A/B comparison evidence ready for semantic alignment."""

    document_a: Document
    document_b: Document
    evidence_a: list[ComparisonEvidence]
    evidence_b: list[ComparisonEvidence]
    coverage_a: DocumentCandidateCoverage
    coverage_b: DocumentCandidateCoverage

    @property
    def all_evidence(self) -> list[ComparisonEvidence]:
        return [
            *self.evidence_a,
            *self.evidence_b,
        ]

    @property
    def evidence_by_id(self) -> dict[str, ComparisonEvidence]:
        return {
            item.source_id: item
            for item in self.all_evidence
        }


def build_owned_document_comparison_candidates(
    *,
    owner_id: int,
    document_a_id: int,
    document_b_id: int,
) -> DocumentComparisonCandidateBundle:
    """Build ordered comparison candidates from two owned documents."""

    document_a, document_b = require_owned_document_pair(
        owner_id=owner_id,
        document_a_id=document_a_id,
        document_b_id=document_b_id,
    )

    raw_a, coverage_a = _build_document_candidates(
        document=document_a,
        owner_id=owner_id,
    )

    raw_b, coverage_b = _build_document_candidates(
        document=document_b,
        owner_id=owner_id,
    )

    evidence_a = _assign_source_ids(
        raw_a,
        side="A",
        document=document_a,
    )

    evidence_b = _assign_source_ids(
        raw_b,
        side="B",
        document=document_b,
    )

    if not evidence_a and not evidence_b:
        raise DocumentComparisonCandidateNotReadyError(
            "Neither selected document contains usable comparison evidence."
        )

    return DocumentComparisonCandidateBundle(
        document_a=document_a,
        document_b=document_b,
        evidence_a=evidence_a,
        evidence_b=evidence_b,
        coverage_a=coverage_a,
        coverage_b=coverage_b,
    )


def build_comparison_evidence_context(
    bundle: DocumentComparisonCandidateBundle,
    *,
    max_characters: int = MAX_COMPARISON_EVIDENCE_CONTEXT_CHARACTERS,
) -> str:
    """Format A/B evidence registries for the comparison model."""

    if max_characters < 2_000:
        raise ValueError(
            "Comparison evidence context must allow at least 2,000 characters."
        )

    header = (
        "DOCUMENT A — BASELINE\n"
        f'Filename: {bundle.document_a.filename}\n'
        f"Analysis status: {bundle.coverage_a.analysis_status}\n"
        f"Evidence mode: {bundle.coverage_a.mode}\n"
        f"Evidence truncated: {'yes' if bundle.coverage_a.truncated else 'no'}\n\n"
        "DOCUMENT B — COMPARE AGAINST A\n"
        f'Filename: {bundle.document_b.filename}\n'
        f"Analysis status: {bundle.coverage_b.analysis_status}\n"
        f"Evidence mode: {bundle.coverage_b.mode}\n"
        f"Evidence truncated: {'yes' if bundle.coverage_b.truncated else 'no'}\n\n"
        "EVIDENCE REGISTRY"
    )

    blocks = [header]
    used = len(header)

    for item in bundle.all_evidence:
        location: list[str] = []

        if item.page is not None:
            location.append(
                f"Page {item.page}"
            )

        if item.section:
            location.append(
                item.section
            )

        location_text = (
            " | ".join(location)
            if location
            else "Location unavailable"
        )

        block_parts = [
            (
                f"[{item.source_id} | "
                f"{item.kind} | "
                f"{location_text}]"
            ),
        ]

        if item.topic:
            block_parts.append(
                f"Topic: {item.topic}"
            )

        if item.statement:
            block_parts.append(
                f"Statement: {item.statement}"
            )

        if item.detail:
            block_parts.append(
                f"Detail: {item.detail}"
            )

        if item.evidence:
            block_parts.append(
                f"Evidence: {item.evidence}"
            )

        block = "\n".join(
            block_parts
        )

        separator = 2
        remaining = (
            max_characters
            - used
            - separator
        )

        if remaining <= 0:
            break

        if len(block) > remaining:
            if remaining < 240:
                break

            block = (
                block[: remaining - 3].rstrip()
                + "..."
            )

        blocks.append(block)
        used += len(block) + separator

    return "\n\n".join(
        blocks
    )


def _build_document_candidates(
    *,
    document: Document,
    owner_id: int,
) -> tuple[
    list[dict[str, Any]],
    DocumentCandidateCoverage,
]:
    analysis_status, analysis = _find_current_analysis(
        document=document,
        owner_id=owner_id,
    )

    structured_all: list[dict[str, Any]] = []

    if analysis is not None:
        structured_all = _structured_candidates_from_analysis(
            analysis
        )

    structured_truncated = (
        len(structured_all)
        > MAX_STRUCTURED_EVIDENCE_PER_SIDE
    )

    structured = structured_all[
        :MAX_STRUCTURED_EVIDENCE_PER_SIDE
    ]

    chunk_limit = (
        MAX_SUPPLEMENTAL_CHUNKS_WITH_ANALYSIS
        if structured
        else MAX_FALLBACK_CHUNKS_WITHOUT_ANALYSIS
    )

    chunk_candidates = _chunk_candidates(
        document=document,
        owner_id=owner_id,
        limit=chunk_limit,
    )

    combined_before_limit = _deduplicate_candidates(
        [
            *structured,
            *chunk_candidates,
        ]
    )

    total_truncated = (
        len(combined_before_limit)
        > MAX_TOTAL_EVIDENCE_PER_SIDE
    )

    combined = combined_before_limit[
        :MAX_TOTAL_EVIDENCE_PER_SIDE
    ]

    if structured and chunk_candidates:
        mode = "structured_plus_chunks"
    elif structured:
        mode = "structured_only"
    elif chunk_candidates:
        mode = "chunks_only"
    else:
        mode = "no_evidence"

    coverage = DocumentCandidateCoverage(
        document_id=document.id,
        filename=document.filename,
        analysis_status=analysis_status,
        analysis_id=(
            analysis.id
            if analysis is not None
            else None
        ),
        structured_evidence_count=sum(
            1
            for item in combined
            if item["origin"] == "structured_analysis"
        ),
        chunk_evidence_count=sum(
            1
            for item in combined
            if item["origin"] == "document_chunk"
        ),
        mode=mode,
        truncated=(
            structured_truncated
            or total_truncated
        ),
    )

    return combined, coverage


def _find_current_analysis(
    *,
    document: Document,
    owner_id: int,
) -> tuple[str, DocumentAIAnalysis | None]:
    analyses = (
        DocumentAIAnalysis.query
        .filter_by(
            document_id=document.id,
            user_id=owner_id,
            status="Completed",
        )
        .order_by(
            DocumentAIAnalysis.created_at.desc(),
            DocumentAIAnalysis.id.desc(),
        )
        .all()
    )

    if not analyses:
        return "Not analysed", None

    current = next(
        (
            analysis
            for analysis in analyses
            if _analysis_is_current(
                document,
                analysis,
            )
        ),
        None,
    )

    if current is not None:
        return "Current", current

    return "Stale", None


def _analysis_is_current(
    document: Document,
    analysis: DocumentAIAnalysis,
) -> bool:
    stored = str(
        analysis.source_fingerprint
        or ""
    ).strip()

    if not stored:
        return False

    extracted_text = str(
        document.extracted_text
        or ""
    ).strip()

    if not extracted_text:
        return False

    legacy = hashlib.sha256(
        extracted_text.encode("utf-8")
    ).hexdigest()

    insights = analysis.insights
    raw_type_metadata = insights.get(
        "type_metadata"
    )

    type_metadata = (
        raw_type_metadata
        if isinstance(
            raw_type_metadata,
            dict,
        )
        else {}
    )

    confirmed_type_key = _compact_text(
        type_metadata.get(
            "confirmed_type_key"
        ),
        80,
    )

    modern_input = (
        f"{DOCUMENT_ANALYSIS_SCHEMA_VERSION}\n"
        f"{confirmed_type_key or 'legacy_unconfirmed'}\n"
        f"{extracted_text}"
    )

    modern = hashlib.sha256(
        modern_input.encode("utf-8")
    ).hexdigest()

    return stored in {
        legacy,
        modern,
    }


def _structured_candidates_from_analysis(
    analysis: DocumentAIAnalysis,
) -> list[dict[str, Any]]:
    insights = analysis.insights
    results: list[dict[str, Any]] = []

    section_specs = (
        (
            "key_point",
            insights.get("key_points"),
            ("title", "text"),
            ("detail", "details"),
        ),
        (
            "requirement",
            insights.get("requirements"),
            ("requirement", "title", "text"),
            ("details", "detail"),
        ),
        (
            "decision",
            insights.get("decisions"),
            ("decision", "title", "text"),
            ("reason", "detail"),
        ),
        (
            "risk",
            insights.get("risks"),
            ("risk", "title", "text"),
            ("impact", "detail"),
        ),
    )

    for (
        kind,
        raw_items,
        statement_keys,
        detail_keys,
    ) in section_specs:
        results.extend(
            _structured_list_candidates(
                kind=kind,
                raw_items=raw_items,
                statement_keys=statement_keys,
                detail_keys=detail_keys,
            )
        )

    for raw_deadline in _as_dict_list(
        insights.get("deadlines")
    ):
        description = _first_text(
            raw_deadline,
            (
                "description",
                "title",
                "text",
            ),
            800,
        )

        date_value = _compact_text(
            raw_deadline.get("date"),
            30,
        )

        statement = (
            f"{description} — {date_value}"
            if description and date_value
            else description or date_value
        )

        candidate = _structured_candidate(
            kind="deadline",
            topic=description or "Deadline",
            statement=statement,
            detail=(
                f"Date: {date_value}"
                if date_value
                else ""
            ),
            source=raw_deadline.get("source"),
        )

        if candidate is not None:
            results.append(candidate)

    for raw_action in _as_dict_list(
        insights.get("action_items")
    ):
        title = _first_text(
            raw_action,
            (
                "title",
                "action",
                "task",
                "text",
            ),
            500,
        )

        description = _first_text(
            raw_action,
            (
                "description",
                "details",
                "detail",
            ),
            1_000,
        )

        extras: list[str] = []

        priority = _compact_text(
            raw_action.get("priority"),
            30,
        )

        deadline = _compact_text(
            raw_action.get("deadline"),
            30,
        )

        if priority:
            extras.append(
                f"Priority: {priority}"
            )

        if deadline:
            extras.append(
                f"Deadline: {deadline}"
            )

        detail = " | ".join(
            value
            for value in (
                description,
                *extras,
            )
            if value
        )

        candidate = _structured_candidate(
            kind="action_item",
            topic=title or "Action item",
            statement=title,
            detail=detail,
            source=raw_action.get("source"),
        )

        if candidate is not None:
            results.append(candidate)

    results.extend(
        _type_specific_candidates(
            insights.get("type_specific")
        )
    )

    return results


def _structured_list_candidates(
    *,
    kind: str,
    raw_items: Any,
    statement_keys: tuple[str, ...],
    detail_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for raw_item in _as_dict_list(
        raw_items
    ):
        statement = _first_text(
            raw_item,
            statement_keys,
            900,
        )

        detail = _first_text(
            raw_item,
            detail_keys,
            1_200,
        )

        candidate = _structured_candidate(
            kind=kind,
            topic=statement or detail,
            statement=statement,
            detail=detail,
            source=raw_item.get("source"),
        )

        if candidate is not None:
            results.append(candidate)

    return results


def _type_specific_candidates(
    value: Any,
) -> list[dict[str, Any]]:
    if not isinstance(
        value,
        dict,
    ):
        return []

    results: list[dict[str, Any]] = []

    for section_key, raw_section in value.items():
        section_label = (
            str(section_key)
            .replace("_", " ")
            .strip()
            .title()
        )

        if isinstance(
            raw_section,
            dict,
        ):
            text = _first_text(
                raw_section,
                (
                    "text",
                    "title",
                    "name",
                    "value",
                ),
                1_000,
            )

            detail = _first_text(
                raw_section,
                (
                    "detail",
                    "details",
                    "description",
                ),
                1_200,
            )

            candidate = _structured_candidate(
                kind=f"type_specific:{section_key}",
                topic=section_label,
                statement=text,
                detail=detail,
                source=raw_section.get("source"),
            )

            if candidate is not None:
                results.append(candidate)

            continue

        if not isinstance(
            raw_section,
            list,
        ):
            continue

        for raw_item in raw_section:
            if not isinstance(
                raw_item,
                dict,
            ):
                continue

            text = _first_text(
                raw_item,
                (
                    "text",
                    "title",
                    "name",
                    "label",
                    "item",
                    "finding",
                    "value",
                ),
                1_000,
            )

            detail = _first_text(
                raw_item,
                (
                    "detail",
                    "details",
                    "description",
                    "reason",
                    "impact",
                ),
                1_200,
            )

            candidate = _structured_candidate(
                kind=f"type_specific:{section_key}",
                topic=section_label,
                statement=text,
                detail=detail,
                source=raw_item.get("source"),
            )

            if candidate is not None:
                results.append(candidate)

    return results


def _structured_candidate(
    *,
    kind: str,
    topic: Any,
    statement: Any,
    detail: Any,
    source: Any,
) -> dict[str, Any] | None:
    source_data = _clean_source(
        source
    )

    cleaned_statement = _compact_text(
        statement,
        1_000,
    )

    cleaned_detail = _compact_text(
        detail,
        1_200,
    )

    if not cleaned_statement and not cleaned_detail:
        return None

    # A comparison finding eventually needs traceable evidence. Keep
    # structured findings only when the saved analysis has at least a page or
    # an evidence excerpt. Otherwise the chunk fallback supplies grounded text.
    if (
        source_data["page"] is None
        and not source_data["evidence"]
    ):
        return None

    return {
        "kind": kind,
        "topic": _compact_text(
            topic,
            500,
        ),
        "statement": cleaned_statement,
        "detail": cleaned_detail,
        "page": source_data["page"],
        "section": source_data["section"],
        "evidence": source_data["evidence"],
        "origin": "structured_analysis",
        "chunk_id": None,
        "chunk_index": None,
    }


def _chunk_candidates(
    *,
    document: Document,
    owner_id: int,
    limit: int,
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []

    try:
        indexed = ensure_owned_document_chunks(
            document_id=document.id,
            user_id=owner_id,
        )

    except (
        DocumentChunkNotFoundError,
        DocumentChunkNotReadyError,
    ):
        return []

    except DocumentChunkError as error:
        raise DocumentComparisonCandidateError(
            "LifeOS could not prepare one of the documents for comparison."
        ) from error

    selected = _select_diverse_chunks(
        indexed.chunks,
        limit=limit,
    )

    results: list[dict[str, Any]] = []

    for chunk in selected:
        clean_text = PAGE_MARKER_PATTERN.sub(
            "",
            str(
                chunk.text
                or ""
            ),
        ).strip()

        if not clean_text:
            continue

        evidence = _compact_text(
            clean_text,
            1_200,
        )

        lines = clean_text.splitlines()

        topic = (
            _compact_text(
                chunk.section_title,
                300,
            )
            or _compact_text(
                lines[0]
                if lines
                else "Document passage",
                300,
            )
        )

        results.append(
            {
                "kind": "chunk",
                "topic": topic,
                "statement": evidence,
                "detail": "",
                "page": _positive_int(
                    chunk.page_start
                ),
                "section": _compact_text(
                    chunk.section_title,
                    300,
                ),
                "evidence": evidence,
                "origin": "document_chunk",
                "chunk_id": chunk.id,
                "chunk_index": chunk.chunk_index,
            }
        )

    return results


def _select_diverse_chunks(
    chunks: list[DocumentChunk],
    *,
    limit: int,
) -> list[DocumentChunk]:
    """Select deterministic document-wide coverage instead of only page one."""

    if limit <= 0 or not chunks:
        return []

    ordered = sorted(
        chunks,
        key=lambda chunk: (
            chunk.chunk_index,
            chunk.id or 0,
        ),
    )

    if len(ordered) <= limit:
        return ordered

    if limit == 1:
        return [
            ordered[
                len(ordered) // 2
            ]
        ]

    positions = {
        round(
            index
            * (
                len(ordered) - 1
            )
            / (
                limit - 1
            )
        )
        for index in range(limit)
    }

    return [
        ordered[position]
        for position in sorted(positions)
    ]


def _assign_source_ids(
    raw_items: list[dict[str, Any]],
    *,
    side: str,
    document: Document,
) -> list[ComparisonEvidence]:
    return [
        ComparisonEvidence(
            source_id=f"{side}{index}",
            side=side,
            document_id=document.id,
            filename=document.filename,
            kind=raw_item["kind"],
            topic=raw_item["topic"],
            statement=raw_item["statement"],
            detail=raw_item["detail"],
            page=raw_item["page"],
            section=raw_item["section"],
            evidence=raw_item["evidence"],
            origin=raw_item["origin"],
            chunk_id=raw_item["chunk_id"],
            chunk_index=raw_item["chunk_index"],
        )
        for index, raw_item in enumerate(
            raw_items,
            start=1,
        )
    ]


def _deduplicate_candidates(
    items: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    for item in items:
        statement = _compact_text(
            item.get("statement"),
            1_000,
        )

        evidence = _compact_text(
            item.get("evidence"),
            1_200,
        )

        key = (
            item.get("kind"),
            _normalise_key(
                statement
                or evidence
            ),
            item.get("page"),
        )

        if not key[1] or key in seen:
            continue

        seen.add(key)
        results.append(item)

    return results


def _clean_source(
    value: Any,
) -> dict[str, Any]:
    source = (
        value
        if isinstance(
            value,
            dict,
        )
        else {}
    )

    return {
        "page": _positive_int(
            source.get("page")
        ),
        "section": _compact_text(
            source.get("section"),
            300,
        ),
        "evidence": _compact_text(
            source.get("evidence"),
            1_200,
        ),
    }


def _first_text(
    value: dict[str, Any],
    keys: tuple[str, ...],
    max_length: int,
) -> str:
    for key in keys:
        candidate = value.get(key)

        if candidate not in (
            None,
            "",
        ):
            cleaned = _compact_text(
                candidate,
                max_length,
            )

            if cleaned:
                return cleaned

    return ""


def _as_dict_list(
    value: Any,
) -> list[dict[str, Any]]:
    if not isinstance(
        value,
        list,
    ):
        return []

    return [
        item
        for item in value
        if isinstance(
            item,
            dict,
        )
    ]


def _compact_text(
    value: Any,
    max_length: int,
) -> str:
    if value is None:
        return ""

    if isinstance(
        value,
        (list, tuple, set),
    ):
        value = "; ".join(
            _compact_text(
                item,
                max_length,
            )
            for item in value
        )

    elif isinstance(
        value,
        dict,
    ):
        value = "; ".join(
            _compact_text(
                item,
                max_length,
            )
            for item in value.values()
        )

    cleaned = " ".join(
        str(
            value
            or ""
        ).split()
    )

    return cleaned[
        :max_length
    ]


def _normalise_key(
    value: Any,
) -> str:
    cleaned = re.sub(
        r"[^\w\s]",
        " ",
        str(
            value
            or ""
        ).casefold(),
        flags=re.UNICODE,
    )

    return " ".join(
        cleaned.split()
    )


def _positive_int(
    value: Any,
) -> int | None:
    try:
        integer = int(value)
    except (
        TypeError,
        ValueError,
    ):
        return None

    return (
        integer
        if integer > 0
        else None
    )
