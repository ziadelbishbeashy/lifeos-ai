"""Deterministic focused evidence previews for Document Brain."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass


DEFAULT_EVIDENCE_PREVIEW_CHARACTERS = 420
MIN_EVIDENCE_PREVIEW_CHARACTERS = 120
MAX_EVIDENCE_PREVIEW_CHARACTERS = 700

PAGE_MARKER_PATTERN = re.compile(
    r"^--- Page\s+\d+\s+---\s*",
    flags=re.MULTILINE,
)

SENTENCE_SPLIT_PATTERN = re.compile(
    r"(?<=[.!?])\s+|\n+",
)

WORD_PATTERN = re.compile(
    r"[^\W_]+(?:['’\-][^\W_]+)*",
    flags=re.UNICODE,
)

STOP_WORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "between",
    "by",
    "can",
    "does",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


@dataclass(frozen=True)
class FocusedEvidencePreview:
    """One bounded excerpt copied from a trusted source chunk."""

    text: str
    focused: bool
    matched_term_count: int
    source_character_count: int


@dataclass(frozen=True)
class _SentenceCandidate:
    """One compact sentence and its position in the source."""

    text: str
    index: int
    start: int
    end: int
    score: float
    matched_term_count: int


def build_focused_evidence_preview(
    source_text: str,
    *,
    question: str = "",
    claim_text: str = "",
    matched_terms: Iterable[str] = (),
    max_characters: int = DEFAULT_EVIDENCE_PREVIEW_CHARACTERS,
) -> FocusedEvidencePreview:
    """
    Return a focused excerpt copied directly from one source chunk.

    The preview is selected deterministically using the question,
    generated claim text and keyword-retrieval terms. No additional
    AI call is made and no evidence wording is invented.
    """

    cleaned_source = _clean_source_text(
        source_text
    )

    cleaned_limit = _validate_limit(
        max_characters
    )

    if not cleaned_source:
        return FocusedEvidencePreview(
            text="",
            focused=False,
            matched_term_count=0,
            source_character_count=0,
        )

    weighted_terms = _weighted_focus_terms(
        question=question,
        claim_text=claim_text,
        matched_terms=matched_terms,
    )

    candidates = _sentence_candidates(
        cleaned_source,
        weighted_terms=weighted_terms,
    )

    if not candidates:
        return FocusedEvidencePreview(
            text=_bounded_excerpt(
                cleaned_source,
                max_characters=cleaned_limit,
                focus_terms=tuple(
                    weighted_terms
                ),
            ),
            focused=False,
            matched_term_count=0,
            source_character_count=len(
                cleaned_source
            ),
        )

    best = max(
        candidates,
        key=lambda candidate: (
            candidate.score,
            candidate.matched_term_count,
            -candidate.index,
        ),
    )

    focused = (
        best.score > 0
        and best.matched_term_count > 0
    )

    if not focused:
        preview = _bounded_excerpt(
            cleaned_source,
            max_characters=cleaned_limit,
            focus_terms=(),
        )

        return FocusedEvidencePreview(
            text=preview,
            focused=False,
            matched_term_count=0,
            source_character_count=len(
                cleaned_source
            ),
        )

    selected = _select_sentence_window(
        candidates,
        best_index=best.index,
        max_characters=cleaned_limit,
    )

    selected_text = " ".join(
        candidate.text
        for candidate in selected
    ).strip()

    selected_start = min(
        candidate.start
        for candidate in selected
    )

    selected_end = max(
        candidate.end
        for candidate in selected
    )

    if len(selected_text) > cleaned_limit:
        selected_text = _bounded_excerpt(
            selected_text,
            max_characters=cleaned_limit,
            focus_terms=tuple(
                weighted_terms
            ),
        )
    else:
        selected_text = _add_context_ellipses(
            selected_text,
            has_before=selected_start > 0,
            has_after=selected_end < len(
                cleaned_source
            ),
            max_characters=cleaned_limit,
        )

    return FocusedEvidencePreview(
        text=selected_text,
        focused=True,
        matched_term_count=best.matched_term_count,
        source_character_count=len(
            cleaned_source
        ),
    )


def _clean_source_text(
    source_text: str,
) -> str:
    """Remove page markers while preserving sentence boundaries."""

    without_markers = PAGE_MARKER_PATTERN.sub(
        "",
        str(source_text or ""),
    )

    lines = [
        " ".join(
            line.split()
        )
        for line in without_markers.splitlines()
    ]

    return "\n".join(
        line
        for line in lines
        if line
    ).strip()


def _validate_limit(
    max_characters: int,
) -> int:
    """Return a bounded preview limit."""

    try:
        parsed = int(
            max_characters
        )
    except (
        TypeError,
        ValueError,
    ):
        parsed = DEFAULT_EVIDENCE_PREVIEW_CHARACTERS

    return max(
        MIN_EVIDENCE_PREVIEW_CHARACTERS,
        min(
            parsed,
            MAX_EVIDENCE_PREVIEW_CHARACTERS,
        ),
    )


def _weighted_focus_terms(
    *,
    question: str,
    claim_text: str,
    matched_terms: Iterable[str],
) -> dict[str, float]:
    """Return normalized focus terms with deterministic weights."""

    weights: dict[str, float] = {}

    def add_terms(
        value: str,
        *,
        weight: float,
    ) -> None:
        for token in _content_tokens(
            value
        ):
            weights[token] = max(
                weights.get(
                    token,
                    0.0,
                ),
                weight,
            )

    add_terms(
        question,
        weight=2.0,
    )

    add_terms(
        claim_text,
        weight=3.0,
    )

    for raw_term in matched_terms or ():
        add_terms(
            str(raw_term or ""),
            weight=5.0,
        )

    return weights


def _content_tokens(
    value: str,
) -> tuple[str, ...]:
    """Return unique meaningful tokens in original order."""

    tokens: list[str] = []
    seen: set[str] = set()

    for match in WORD_PATTERN.finditer(
        str(value or "").casefold()
    ):
        token = match.group(0).strip(
            "'’-"
        )

        if (
            not token
            or token in STOP_WORDS
            or (
                len(token) < 3
                and not token.isdigit()
            )
            or token in seen
        ):
            continue

        seen.add(token)
        tokens.append(token)

    return tuple(
        tokens
    )


def _sentence_candidates(
    source_text: str,
    *,
    weighted_terms: dict[str, float],
) -> list[_SentenceCandidate]:
    """Split the source and score each sentence-like segment."""

    raw_segments = [
        " ".join(
            segment.split()
        ).strip()
        for segment in SENTENCE_SPLIT_PATTERN.split(
            source_text
        )
    ]

    segments = [
        segment
        for segment in raw_segments
        if segment
    ]

    candidates: list[_SentenceCandidate] = []
    search_from = 0

    for index, sentence in enumerate(
        segments
    ):
        start = source_text.find(
            sentence,
            search_from,
        )

        if start < 0:
            start = search_from

        end = start + len(
            sentence
        )

        search_from = end

        sentence_tokens = set(
            _content_tokens(
                sentence
            )
        )

        matching_terms = [
            term
            for term in weighted_terms
            if term in sentence_tokens
        ]

        score = sum(
            weighted_terms[term]
            for term in matching_terms
        )

        # Prefer a compact sentence when two candidates contain the
        # same evidence terms.
        if score > 0:
            score += max(
                0.0,
                1.0 - len(sentence) / 1000.0,
            )

        candidates.append(
            _SentenceCandidate(
                text=sentence,
                index=index,
                start=start,
                end=end,
                score=score,
                matched_term_count=len(
                    matching_terms
                ),
            )
        )

    return candidates


def _select_sentence_window(
    candidates: list[_SentenceCandidate],
    *,
    best_index: int,
    max_characters: int,
) -> list[_SentenceCandidate]:
    """
    Grow one contiguous window around the strongest sentence.

    The preview never joins separated source passages. This keeps the
    displayed evidence a genuine continuous excerpt from the chunk.
    """

    left = best_index
    right = best_index

    def window_length(
        start: int,
        end: int,
    ) -> int:
        return len(
            " ".join(
                candidate.text
                for candidate in candidates[
                    start:end + 1
                ]
            )
        )

    included_adjacent_context = False

    while True:
        options: list[
            tuple[float, int, str]
        ] = []

        if left > 0:
            options.append(
                (
                    candidates[
                        left - 1
                    ].score,
                    -1,
                    "left",
                )
            )

        if right + 1 < len(
            candidates
        ):
            options.append(
                (
                    candidates[
                        right + 1
                    ].score,
                    -1,
                    "right",
                )
            )

        if not options:
            break

        options.sort(
            reverse=True
        )

        added = False

        for score, _distance, direction in options:
            next_left = (
                left - 1
                if direction == "left"
                else left
            )

            next_right = (
                right + 1
                if direction == "right"
                else right
            )

            tentative_length = window_length(
                next_left,
                next_right,
            )

            should_include = (
                score > 0
                or not included_adjacent_context
            )

            if (
                should_include
                and tentative_length
                <= max_characters - 8
            ):
                left = next_left
                right = next_right
                included_adjacent_context = True
                added = True
                break

        if not added:
            break

        if window_length(
            left,
            right,
        ) >= (
            max_characters * 0.78
        ):
            break

    return candidates[
        left:right + 1
    ]


def _bounded_excerpt(
    text: str,
    *,
    max_characters: int,
    focus_terms: tuple[str, ...],
) -> str:
    """Return a word-safe excerpt around the first useful focus term."""

    compact = " ".join(
        str(text or "").split()
    )

    if len(compact) <= max_characters:
        return compact

    folded = compact.casefold()
    focus_position: int | None = None

    for term in focus_terms:
        position = folded.find(
            term.casefold()
        )

        if (
            position >= 0
            and (
                focus_position is None
                or position < focus_position
            )
        ):
            focus_position = position

    if focus_position is None:
        start = 0
    else:
        start = max(
            0,
            focus_position
            - max_characters // 3,
        )

    end = min(
        len(compact),
        start + max_characters,
    )

    if end - start < max_characters:
        start = max(
            0,
            end - max_characters,
        )

    if start > 0:
        next_space = compact.find(
            " ",
            start,
        )

        if (
            next_space >= 0
            and next_space < end
        ):
            start = next_space + 1

    if end < len(compact):
        previous_space = compact.rfind(
            " ",
            start,
            end,
        )

        if previous_space > start:
            end = previous_space

    excerpt = compact[
        start:end
    ].strip()

    return _add_context_ellipses(
        excerpt,
        has_before=start > 0,
        has_after=end < len(compact),
        max_characters=max_characters,
    )


def _add_context_ellipses(
    text: str,
    *,
    has_before: bool,
    has_after: bool,
    max_characters: int,
) -> str:
    """Add bounded ellipses when surrounding source text was omitted."""

    prefix = "… " if has_before else ""
    suffix = " …" if has_after else ""

    available = max(
        0,
        max_characters
        - len(prefix)
        - len(suffix),
    )

    core = str(
        text or ""
    ).strip()

    if len(core) > available:
        core = core[
            :available
        ].rstrip()

        last_space = core.rfind(
            " "
        )

        if last_space > 0:
            core = core[
                :last_space
            ].rstrip()

    return (
        prefix
        + core
        + suffix
    ).strip()
