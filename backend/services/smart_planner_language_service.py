"""Deterministic natural-language understanding for V-SPACE Smart Planner V1.

Stage 3 deliberately keeps language understanding separate from scheduling and
persistence.  This parser extracts only high-confidence planning constraints;
the deterministic Smart Planner still owns time arithmetic and I9 still owns
accepted-plan mutations.

The parser never writes to the database and never sends user text to a public
search provider.  Ambiguous phrases stay in ``request_text`` for prioritisation
rather than being invented into calendar facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta, time
import re
from typing import Any


MAX_FOCUS_REQUESTS = 8
MAX_INTERPRETED_COMMITMENTS = 8
MAX_FOCUS_MINUTES = 8 * 60
MAX_HORIZON_DAYS = 14


_TIME_TOKEN = r"(?:[01]?\d|2[0-3])(?::[0-5]\d)?\s*(?:a\.?m\.?|p\.?m\.?)?"
_DURATION_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>hours?|hrs?|hr|h|minutes?|mins?|min|m)\b",
    re.IGNORECASE,
)


class PlannerLanguageError(ValueError):
    pass


@dataclass(frozen=True)
class InterpretedCommitment:
    title: str
    date: date
    start_time: time | None
    end_time: time
    commitment_type: str = "other"
    assumption: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "date": self.date.isoformat(),
            "start_time": self.start_time.strftime("%H:%M") if self.start_time else None,
            "end_time": self.end_time.strftime("%H:%M"),
            "commitment_type": self.commitment_type,
            "source": "interpreted",
            "editable": False,
        }


@dataclass(frozen=True)
class FocusRequest:
    title: str
    minutes: int
    source_text: str

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "minutes": self.minutes, "source_text": self.source_text}


@dataclass(frozen=True)
class PlannerLanguageInterpretation:
    text: str
    mode: str | None = None
    start_date: date | None = None
    horizon_days: int | None = None
    energy_mode: str = "normal"
    rebalance_requested: bool = False
    from_now: bool = False
    commitments: tuple[InterpretedCommitment, ...] = ()
    focus_requests: tuple[FocusRequest, ...] = ()
    priority_terms: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()

    @property
    def understood(self) -> bool:
        return bool(
            self.mode
            or self.start_date
            or self.horizon_days
            or self.energy_mode != "normal"
            or self.rebalance_requested
            or self.commitments
            or self.focus_requests
            or self.priority_terms
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "mode": self.mode,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "horizon_days": self.horizon_days,
            "energy_mode": self.energy_mode,
            "rebalance_requested": self.rebalance_requested,
            "from_now": self.from_now,
            "commitments": [item.to_dict() for item in self.commitments],
            "focus_requests": [item.to_dict() for item in self.focus_requests],
            "priority_terms": list(self.priority_terms),
            "assumptions": list(self.assumptions),
            "understood": self.understood,
        }


def _clean(value: Any, *, limit: int = 600) -> str:
    return " ".join(str(value or "").split())[:limit].strip()


def _parse_clock(token: str) -> time | None:
    raw = _clean(token, limit=32).lower().replace(".", "")
    if not raw:
        return None
    meridiem = None
    if raw.endswith("am") or raw.endswith("pm"):
        meridiem = raw[-2:]
        raw = raw[:-2].strip()
    try:
        if ":" in raw:
            hour_text, minute_text = raw.split(":", 1)
            hour, minute = int(hour_text), int(minute_text)
        else:
            hour, minute = int(raw), 0
    except (TypeError, ValueError):
        return None
    if meridiem:
        if not 1 <= hour <= 12:
            return None
        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)


def _duration_minutes(value: str, unit: str) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    normalized = unit.lower()
    minutes = round(number * 60) if normalized.startswith("h") else round(number)
    return max(5, min(minutes, MAX_FOCUS_MINUTES))


def _next_weekday(anchor: date, weekday: int, *, include_today: bool = False) -> date:
    delta = (weekday - anchor.weekday()) % 7
    if delta == 0 and not include_today:
        delta = 7
    return anchor + timedelta(days=delta)


def _extract_start_date(text: str, *, anchor: date) -> tuple[date | None, list[str]]:
    lower = text.lower()
    assumptions: list[str] = []
    # When both today and tomorrow appear (for example "light today, move hard
    # tasks tomorrow"), today is the plan anchor and tomorrow is only context.
    if re.search(r"\btoday\b", lower):
        return anchor, assumptions
    if re.search(r"\btomorrow\b", lower):
        target = anchor + timedelta(days=1)
        assumptions.append(f'Interpreted "tomorrow" as {target.isoformat()}.')
        return target, assumptions

    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    # Only treat a weekday as the plan start when the user explicitly frames it
    # as the plan/schedule day. "exam on Monday" and "before Friday" are not
    # start-date instructions.
    patterns = (
        r"\b(?:plan|schedule)(?:\s+my)?\s+(?:day\s+)?(?:for|on)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\b(?:this|next)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(?:plan|schedule)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, lower)
        if not match:
            continue
        weekday_name = match.group(1)
        target = _next_weekday(anchor, weekdays[weekday_name], include_today="this " in match.group(0))
        assumptions.append(f'Interpreted the requested {weekday_name.title()} plan as {target.isoformat()}.')
        return target, assumptions
    return None, assumptions

def _extract_mode_horizon(text: str, *, anchor: date, start_date: date | None) -> tuple[str | None, int | None, list[str]]:
    lower = text.lower()
    assumptions: list[str] = []
    next_days = re.search(r"\b(?:next|over the next|for the next)\s+(\d{1,2})\s+days?\b", lower)
    if next_days:
        days = max(2, min(int(next_days.group(1)), MAX_HORIZON_DAYS))
        assumptions.append(f"Using a {days}-day goal horizon from your request.")
        return "goal", days, assumptions
    if re.search(r"\b(?:this|my|the|next)?\s*week\b", lower):
        return "week", 7, assumptions
    if any(phrase in lower for phrase in ("goal plan", "finish in ", "ready in ", "within ")):
        duration = re.search(r"\b(?:in|within)\s+(\d{1,2})\s+days?\b", lower)
        if duration:
            days = max(2, min(int(duration.group(1)), MAX_HORIZON_DAYS))
            return "goal", days, assumptions
        return "goal", 7, assumptions

    before_day = re.search(r"\b(?:before|by)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lower)
    if before_day:
        weekdays = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
        origin = start_date or anchor
        target = _next_weekday(origin, weekdays[before_day.group(1)], include_today=True)
        horizon = max(2, min((target - origin).days + 1, MAX_HORIZON_DAYS))
        assumptions.append(f"Planning through {before_day.group(1).title()} to respect the requested target window.")
        return "goal", horizon, assumptions
    return None, None, assumptions


def _extract_energy_mode(text: str) -> tuple[str, list[str]]:
    lower = text.lower()
    if any(term in lower for term in ("i'm tired", "i am tired", "low energy", "lighter plan", "light day", "take it easy", "easy day")):
        return "light", ["Using a lighter day: V-SPACE will intentionally leave recovery capacity instead of filling every free minute."]
    if any(term in lower for term in ("intense day", "deep work day", "push today", "packed day", "maximize today", "maximise today")):
        return "intense", ["Using an intense day while still respecting fixed commitments and the working window."]
    return "normal", []


def _commitment_title(kind: str) -> str:
    normalized = kind.lower()
    if normalized == "busy":
        return "Unavailable"
    if normalized == "work":
        return "Work commitment"
    return normalized.title()


def _extract_commitments(text: str, *, target_date: date) -> tuple[list[InterpretedCommitment], list[str]]:
    results: list[InterpretedCommitment] = []
    assumptions: list[str] = []
    occupied_spans: list[tuple[int, int]] = []

    range_pattern = re.compile(
        rf"\b(?P<kind>university|school|class|meeting|exam|appointment|work|busy)\b[^,.]{{0,28}}?\b(?:from\s+)?(?P<start>{_TIME_TOKEN})\s*(?:to|until|[-–])\s*(?P<end>{_TIME_TOKEN})",
        re.IGNORECASE,
    )
    for match in range_pattern.finditer(text):
        start_at, end_at = _parse_clock(match.group("start")), _parse_clock(match.group("end"))
        if not start_at or not end_at or end_at <= start_at:
            continue
        kind = match.group("kind").lower()
        results.append(InterpretedCommitment(
            title=_commitment_title(kind),
            date=target_date,
            start_time=start_at,
            end_time=end_at,
            commitment_type="class" if kind in {"university", "school", "class"} else kind if kind in {"meeting", "exam", "appointment"} else "other",
        ))
        occupied_spans.append(match.span())
        assumptions.append(f"Blocked {start_at.strftime('%H:%M')}–{end_at.strftime('%H:%M')} for {_commitment_title(kind).lower()}.")
        if len(results) >= MAX_INTERPRETED_COMMITMENTS:
            return results, assumptions

    until_pattern = re.compile(
        rf"\b(?P<kind>university|school|class|work|busy)\b[^,.]{{0,32}}?\buntil\s+(?P<end>{_TIME_TOKEN})",
        re.IGNORECASE,
    )
    for match in until_pattern.finditer(text):
        if any(match.start() >= start and match.end() <= end for start, end in occupied_spans):
            continue
        end_at = _parse_clock(match.group("end"))
        if not end_at:
            continue
        kind = match.group("kind").lower()
        results.append(InterpretedCommitment(
            title=_commitment_title(kind),
            date=target_date,
            start_time=None,
            end_time=end_at,
            commitment_type="class" if kind in {"university", "school", "class"} else "other",
            assumption="start_at_working_window",
        ))
        assumptions.append(f"Treated {_commitment_title(kind).lower()} as unavailable time until {end_at.strftime('%H:%M')}; its start will use your planner working start.")
        if len(results) >= MAX_INTERPRETED_COMMITMENTS:
            break
    return results, assumptions


def _clean_focus_title(raw: str) -> str:
    text = _clean(raw, limit=100)
    text = re.sub(r"^(?:the\s+)?(?:project\s+)?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:and then|then|after that)$", "", text, flags=re.IGNORECASE).strip(" ,.;:-")
    return text[:80]


def _extract_focus_requests(text: str) -> tuple[list[FocusRequest], list[str]]:
    results: list[FocusRequest] = []
    assumptions: list[str] = []
    seen: set[tuple[str, int]] = set()

    patterns = [
        re.compile(
            r"(?P<duration>\d+(?:\.\d+)?\s*(?:hours?|hrs?|hr|h|minutes?|mins?|min|m))\s+(?:for|on)\s+(?P<title>[^,.;]+?)(?=(?:\s+and\s+\d|\s+then\b|[,.;]|$))",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:work\s+on|study|revise|review|focus\s+on)\s+(?P<title>[^,.;]+?)\s+for\s+(?P<duration>\d+(?:\.\d+)?\s*(?:hours?|hrs?|hr|h|minutes?|mins?|min|m))",
            re.IGNORECASE,
        ),
    ]
    for pattern in patterns:
        for match in pattern.finditer(text):
            duration_match = _DURATION_RE.search(match.group("duration"))
            if not duration_match:
                continue
            minutes = _duration_minutes(duration_match.group("value"), duration_match.group("unit"))
            title = _clean_focus_title(match.group("title"))
            if not minutes or not title:
                continue
            key = (title.casefold(), minutes)
            if key in seen:
                continue
            seen.add(key)
            results.append(FocusRequest(title=title, minutes=minutes, source_text=_clean(match.group(0), limit=180)))
            assumptions.append(f"Reserved {minutes} minutes of focused work for {title}.")
            if len(results) >= MAX_FOCUS_REQUESTS:
                return results, assumptions
    return results, assumptions


def _extract_priority_terms(text: str) -> tuple[str, ...]:
    patterns = (
        r"\b(?:must|need to|have to|make sure (?:i|we)?)\s+(?:finish|complete|do|work on|study|revise)\s+([^,.;]+)",
        r"\b(?:priority|prioritize|prioritise)\s+([^,.;]+)",
    )
    items: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            item = _clean_focus_title(match.group(1))
            item = re.split(r"\b(?:before|by|tomorrow|today|this week|next week)\b", item, maxsplit=1, flags=re.IGNORECASE)[0].strip()
            if item and item.casefold() not in {value.casefold() for value in items}:
                items.append(item[:100])
            if len(items) >= 6:
                return tuple(items)
    return tuple(items)


def interpret_planner_request(text: str, *, anchor_date: date | None = None) -> PlannerLanguageInterpretation:
    cleaned = _clean(text, limit=1200)
    if not cleaned:
        return PlannerLanguageInterpretation(text="")
    anchor = anchor_date or date.today()
    assumptions: list[str] = []

    start_date, notes = _extract_start_date(cleaned, anchor=anchor)
    assumptions.extend(notes)
    target_date = start_date or anchor
    mode, horizon_days, notes = _extract_mode_horizon(cleaned, anchor=anchor, start_date=start_date)
    assumptions.extend(notes)
    energy_mode, notes = _extract_energy_mode(cleaned)
    assumptions.extend(notes)
    commitments, notes = _extract_commitments(cleaned, target_date=target_date)
    assumptions.extend(notes)
    focus_requests, notes = _extract_focus_requests(cleaned)
    assumptions.extend(notes)
    priority_terms = _extract_priority_terms(cleaned)

    lower = cleaned.lower()
    rebalance_requested = any(term in lower for term in (
        "replan", "rebalance", "plan the rest", "rest of today", "missed the morning",
        "missed my morning", "running late", "fell behind",
    ))
    from_now = rebalance_requested and any(term in lower for term in ("today", "morning", "running late", "fell behind", "rest"))
    if rebalance_requested:
        assumptions.append("Interpreted this as a request to rebalance the current accepted plan rather than replace completed work.")

    # Day is the safe default when the text explicitly names today/tomorrow and
    # did not independently ask for a multi-day horizon.
    if mode is None and start_date is not None:
        mode = "day"

    return PlannerLanguageInterpretation(
        text=cleaned,
        mode=mode,
        start_date=start_date,
        horizon_days=horizon_days,
        energy_mode=energy_mode,
        rebalance_requested=rebalance_requested,
        from_now=from_now,
        commitments=tuple(commitments),
        focus_requests=tuple(focus_requests),
        priority_terms=priority_terms,
        assumptions=tuple(assumptions[:16]),
    )
