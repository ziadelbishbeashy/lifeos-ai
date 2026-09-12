"""Deterministic course discovery and learning personalization for Private Tutor.

This service does not answer course questions and does not create a second AI/RAG
stack.  It only interprets user-owned module metadata and deterministic Tutor
history/mastery so the existing Private Tutor can choose the right course,
difficulty, and next learning action.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Any

from models import PrivateTutorMastery, PrivateTutorSession
from services.module_question_workflow_service import (
    ModuleQuestionNotFoundError,
    list_owned_module_scope_documents,
)
from services.module_service import ModuleNotFoundError, list_owned_modules, require_owned_module


MAX_INTENT_CHARACTERS = 500
_MATCH_THRESHOLD = 48
_AMBIGUOUS_MARGIN = 18
_STOPWORDS = {
    "a", "an", "and", "are", "at", "be", "for", "from", "help", "i", "in", "is",
    "learn", "learning", "me", "my", "of", "on", "please", "review", "study", "studying",
    "teach", "the", "this", "to", "today", "want", "with", "would",
}


class TutorPersonalizationError(RuntimeError):
    pass


class TutorPersonalizationNotFoundError(TutorPersonalizationError):
    pass


class TutorPersonalizationValidationError(TutorPersonalizationError, ValueError):
    pass


def _clean_intent(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        raise TutorPersonalizationValidationError("Tell Private Tutor what you want to study.")
    if len(text) > MAX_INTENT_CHARACTERS:
        raise TutorPersonalizationValidationError("Study request is too long.")
    return text


def _normalized(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "").lower())
    raw = "".join(char for char in raw if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", raw).strip()


def _tokens(value: Any) -> set[str]:
    return {
        token
        for token in _normalized(value).split()
        if token not in _STOPWORDS and (len(token) >= 3 or token.isdigit())
    }


def _module_match_score(module, request_text: str) -> tuple[int, list[str]]:
    request_normalized = _normalized(request_text)
    request_tokens = _tokens(request_text)
    title = _normalized(module.title)
    subject = _normalized(module.subject)
    title_tokens = _tokens(module.title)
    subject_tokens = _tokens(module.subject)
    score = 0
    reasons: list[str] = []

    if title and title in request_normalized:
        score += 105
        reasons.append("module title appears in your request")
    if subject and subject in request_normalized and subject != title:
        score += 85
        reasons.append("module subject appears in your request")

    title_overlap = request_tokens & title_tokens
    subject_overlap = request_tokens & subject_tokens
    if title_overlap:
        score += min(55, 24 * len(title_overlap))
        if title_tokens and title_tokens.issubset(request_tokens):
            score += 24
        reasons.append("matching module keywords")
    if subject_overlap:
        score += min(40, 20 * len(subject_overlap))
        if subject_tokens and subject_tokens.issubset(request_tokens):
            score += 18
        reasons.append("matching subject keywords")

    # Description can break ties but must never be enough by itself for an
    # automatic course selection.
    description_overlap = request_tokens & _tokens(module.description)
    score += min(12, 4 * len(description_overlap))
    return score, list(dict.fromkeys(reasons))


def _candidate_payload(module, *, score: int, reasons: list[str]) -> dict[str, Any]:
    return {
        "id": module.id,
        "title": module.title,
        "subject": module.subject,
        "status": module.status,
        "score": score,
        "confidence": round(min(1.0, score / 140), 2),
        "match_reasons": reasons,
    }


def resolve_owned_study_intent(*, user_id: int, request_text: Any) -> dict[str, Any]:
    """Resolve a natural study request to an owned module without using an LLM."""

    clean_request = _clean_intent(request_text)
    ranked: list[tuple[int, Any, list[str]]] = []
    for module in list_owned_modules(user_id):
        score, reasons = _module_match_score(module, clean_request)
        if score > 0:
            ranked.append((score, module, reasons))
    ranked.sort(key=lambda item: (item[0], getattr(item[1], "updated_at", datetime.min)), reverse=True)

    candidates = [_candidate_payload(module, score=score, reasons=reasons) for score, module, reasons in ranked[:5]]
    if not ranked or ranked[0][0] < _MATCH_THRESHOLD:
        return {
            "status": "no_match",
            "request_text": clean_request,
            "selected_module_id": None,
            "confidence": 0.0,
            "candidates": candidates,
            "message": "I couldn't confidently match that request to one of your course workspaces.",
        }

    top_score, top_module, top_reasons = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0
    if second_score >= _MATCH_THRESHOLD and (top_score - second_score) < _AMBIGUOUS_MARGIN:
        return {
            "status": "ambiguous",
            "request_text": clean_request,
            "selected_module_id": None,
            "confidence": round(min(1.0, top_score / 140), 2),
            "candidates": candidates,
            "message": "I found more than one course that could match. Choose the one you mean.",
        }

    return {
        "status": "matched",
        "request_text": clean_request,
        "selected_module_id": top_module.id,
        "confidence": round(min(1.0, top_score / 140), 2),
        "match_reasons": top_reasons,
        "candidates": candidates,
        "message": f"I matched this study request to {top_module.title}.",
    }


def _weighted_mastery(rows: list[PrivateTutorMastery]) -> int | None:
    total_questions = sum(max(0, int(row.question_count or 0)) for row in rows)
    if total_questions:
        total_correct = sum(max(0, int(row.correct_count or 0)) for row in rows)
        return round((total_correct / total_questions) * 100)
    if rows:
        return round(sum(int(row.mastery_score or 0) for row in rows) / len(rows))
    return None


def _study_streak_days(sessions: list[PrivateTutorSession]) -> int:
    days = {row.created_at.date() for row in sessions if row.created_at is not None}
    if not days:
        return 0
    cursor = date.today()
    # A late-night user should not lose a visible streak merely because today's
    # study session has not happened yet.
    if cursor not in days:
        cursor -= timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _assessment_target(assessment):
    return getattr(assessment, "assessment_date", None) or getattr(assessment, "due_date", None)


def _upcoming_assessment(module) -> dict[str, Any] | None:
    today = date.today()
    future = []
    for assessment in list(getattr(module, "assessments", []) or []):
        target = _assessment_target(assessment)
        if target is not None and target >= today and str(getattr(assessment, "status", "")).lower() not in {"completed", "done"}:
            future.append((target, assessment))
    if not future:
        return None
    target, assessment = min(future, key=lambda item: item[0])
    return {
        "id": assessment.id,
        "title": assessment.title,
        "type": assessment.assessment_type,
        "target_date": target.isoformat(),
        "days_until": (target - today).days,
        "topics": assessment.topics,
    }


def _session_summary(row: PrivateTutorSession | None) -> dict[str, Any] | None:
    if row is None:
        return None
    percentage = None
    if row.score_correct is not None and row.score_total:
        percentage = round((row.score_correct / row.score_total) * 100)
    return {
        "id": row.id,
        "mode": row.mode,
        "difficulty": row.difficulty,
        "topic": row.topic,
        "title": row.content.get("title") or (row.topic or "Study session"),
        "score_percentage": percentage,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _mastery_payload(row: PrivateTutorMastery) -> dict[str, Any]:
    return {
        "id": row.id,
        "topic": row.topic_label,
        "topic_key": row.topic_key,
        "mastery_score": int(row.mastery_score or 0),
        "last_percentage": int(row.last_percentage or 0),
        "best_percentage": int(row.best_percentage or 0),
        "quiz_attempts": int(row.quiz_attempts or 0),
        "question_count": int(row.question_count or 0),
    }


def _recommendation(*, module, document_count: int, mastery_rows: list[PrivateTutorMastery], session_count: int, upcoming_assessment: dict[str, Any] | None) -> dict[str, Any]:
    if document_count == 0:
        return {
            "action": "add_material",
            "mode": None,
            "difficulty": "adaptive",
            "topic": None,
            "title": "Add course material",
            "reason": "This course workspace has no searchable study documents yet.",
            "request_text": None,
        }

    weak = sorted(mastery_rows, key=lambda row: (int(row.mastery_score or 0), -(int(row.question_count or 0))))
    if weak:
        weakest = weak[0]
        score = int(weakest.mastery_score or 0)
        if score < 50:
            mode = "explain"
            title = f"Rebuild {weakest.topic_label}"
            reason = f"Your current mastery is {score}%, so understanding should come before another full quiz."
        elif score < 75:
            mode = "practice"
            title = f"Practice {weakest.topic_label}"
            reason = f"Your current mastery is {score}%; targeted practice is the fastest next step."
        else:
            mode = "quiz"
            title = "Test your strongest remaining gaps"
            reason = "Your tracked topics are mostly strong, so an adaptive quiz can find the next gap."
        return {
            "action": "start_session",
            "mode": mode,
            "difficulty": "adaptive",
            "topic": weakest.topic_label,
            "title": title,
            "reason": reason,
            "request_text": f"Help me improve {weakest.topic_label} using my {module.title} material.",
        }

    if upcoming_assessment is not None and upcoming_assessment["days_until"] <= 14:
        topic = str(upcoming_assessment.get("topics") or "").strip() or None
        return {
            "action": "start_session",
            "mode": "quiz",
            "difficulty": "adaptive",
            "topic": topic,
            "title": f"Prepare for {upcoming_assessment['title']}",
            "reason": f"This assessment is in {upcoming_assessment['days_until']} day(s), so a baseline quiz will reveal what to revise.",
            "request_text": f"Prepare me for {upcoming_assessment['title']} using my course material.",
        }

    if session_count == 0:
        return {
            "action": "start_session",
            "mode": "explain",
            "difficulty": "adaptive",
            "topic": None,
            "title": "Build your course baseline",
            "reason": "You have course material but no Tutor history yet. Start with the core concepts, then quiz yourself.",
            "request_text": f"Teach me the most important concepts in {module.title}, then give me a short self-check.",
        }

    return {
        "action": "start_session",
        "mode": "quiz",
        "difficulty": "adaptive",
        "topic": None,
        "title": "Run an adaptive knowledge check",
        "reason": "You have study history but no tracked quiz mastery yet. A short quiz will create a useful baseline.",
        "request_text": f"Quiz me across the important concepts in {module.title} and identify my weakest areas.",
    }


def build_owned_course_profile(*, user_id: int, module_id: int) -> dict[str, Any]:
    try:
        module = require_owned_module(int(module_id), user_id)
    except (ModuleNotFoundError, TypeError, ValueError) as error:
        raise TutorPersonalizationNotFoundError("Module not found.") from error

    try:
        documents = list_owned_module_scope_documents(module_id=module.id, user_id=user_id, lecture_id=None)
    except ModuleQuestionNotFoundError as error:
        raise TutorPersonalizationNotFoundError(str(error)) from error

    sessions = (
        PrivateTutorSession.query
        .filter_by(user_id=user_id, module_id=module.id)
        .order_by(PrivateTutorSession.created_at.desc(), PrivateTutorSession.id.desc())
        .limit(200)
        .all()
    )
    mastery_rows = (
        PrivateTutorMastery.query
        .filter_by(user_id=user_id, module_id=module.id)
        .order_by(PrivateTutorMastery.mastery_score.asc(), PrivateTutorMastery.updated_at.desc())
        .all()
    )
    overall = _weighted_mastery(mastery_rows)
    weak_rows = [row for row in mastery_rows if int(row.mastery_score or 0) < 70][:5]
    strong_rows = sorted(
        [row for row in mastery_rows if int(row.mastery_score or 0) >= 80],
        key=lambda row: int(row.mastery_score or 0), reverse=True,
    )[:5]
    assessment = _upcoming_assessment(module)
    document_count = len(documents)
    quiz_count = sum(1 for row in sessions if row.mode == "quiz" and row.status == "graded")
    if document_count and (sessions or mastery_rows):
        expertise = "personalized_course_expert"
        expertise_label = "Personalized course expert"
    elif document_count:
        expertise = "course_expert"
        expertise_label = "Course expert"
    else:
        expertise = "course_workspace"
        expertise_label = "Course workspace"

    return {
        "module": {
            "id": module.id,
            "title": module.title,
            "subject": module.subject,
            "status": module.status,
        },
        "expertise": expertise,
        "expertise_label": expertise_label,
        "expert_ready": document_count > 0,
        "personalized": bool(sessions or mastery_rows),
        "counts": {
            "lectures": len(list(getattr(module, "lectures", []) or [])),
            "documents": document_count,
            "sessions": len(sessions),
            "graded_quizzes": quiz_count,
            "mastery_topics": len(mastery_rows),
        },
        "overall_mastery": overall,
        "weak_topics": [_mastery_payload(row) for row in weak_rows],
        "strong_topics": [_mastery_payload(row) for row in strong_rows],
        "study_streak_days": _study_streak_days(sessions),
        "study_days_last_30": len({row.created_at.date() for row in sessions if row.created_at and row.created_at.date() >= date.today() - timedelta(days=29)}),
        "last_session": _session_summary(sessions[0] if sessions else None),
        "upcoming_assessment": assessment,
        "recommendation": _recommendation(
            module=module,
            document_count=document_count,
            mastery_rows=mastery_rows,
            session_count=len(sessions),
            upcoming_assessment=assessment,
        ),
    }


def _matching_mastery_row(rows: list[PrivateTutorMastery], topic: str | None) -> PrivateTutorMastery | None:
    topic_tokens = _tokens(topic)
    if not topic_tokens:
        return None
    ranked: list[tuple[float, PrivateTutorMastery]] = []
    normalized_topic = _normalized(topic)
    for row in rows:
        label = _normalized(row.topic_label)
        row_tokens = _tokens(row.topic_label)
        if label and label in normalized_topic:
            ranked.append((2.0, row))
            continue
        overlap = len(topic_tokens & row_tokens)
        if overlap:
            ranked.append((overlap / max(1, len(row_tokens)), row))
    return max(ranked, key=lambda item: item[0])[1] if ranked else None


def resolve_adaptive_difficulty(*, user_id: int, module_id: int, topic: str | None = None) -> dict[str, Any]:
    rows = PrivateTutorMastery.query.filter_by(user_id=user_id, module_id=module_id).all()
    matched = _matching_mastery_row(rows, topic)
    if matched is not None:
        score = int(matched.mastery_score or 0)
        basis = matched.topic_label
    else:
        weighted = _weighted_mastery(rows)
        score = weighted if weighted is not None else None
        basis = "overall course mastery"

    if score is None:
        return {
            "difficulty": "intermediate",
            "score": None,
            "basis": "no mastery baseline yet",
            "reason": "No quiz mastery exists yet, so V-SPACE starts at an intermediate baseline and adapts after grading.",
        }
    if score < 45:
        difficulty = "beginner"
    elif score < 80:
        difficulty = "intermediate"
    else:
        difficulty = "advanced"
    return {
        "difficulty": difficulty,
        "score": score,
        "basis": basis,
        "reason": f"Adaptive difficulty selected {difficulty} from {basis} at {score}% mastery.",
    }


def build_tutor_personalization_context(*, user_id: int, module_id: int, topic: str | None = None) -> dict[str, Any]:
    """Return deterministic learning history for pedagogy, never as course evidence."""

    profile = build_owned_course_profile(user_id=user_id, module_id=module_id)
    adaptive = resolve_adaptive_difficulty(user_id=user_id, module_id=module_id, topic=topic)
    return {
        "expertise": profile["expertise"],
        "overall_mastery": profile["overall_mastery"],
        "weak_topics": [item["topic"] for item in profile["weak_topics"][:4]],
        "strong_topics": [item["topic"] for item in profile["strong_topics"][:4]],
        "previous_sessions": profile["counts"]["sessions"],
        "graded_quizzes": profile["counts"]["graded_quizzes"],
        "study_streak_days": profile["study_streak_days"],
        "adaptive": adaptive,
        "recommendation": profile["recommendation"],
    }
