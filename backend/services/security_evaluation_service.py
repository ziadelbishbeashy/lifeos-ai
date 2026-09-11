"""Step 19 synthetic prompt-injection evaluation.

This is intentionally separate from production RAG. It exercises the same
``ask_document_question`` prompt/validation path with synthetic untrusted
sources so regressions in prompt boundaries can be caught without touching user
content.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from services.ai_service import AIServiceError, ask_document_question
from services.document_security_service import (
    assess_untrusted_content,
    source_ids_within_range,
)


_SOURCE_RE = re.compile(r"^\[Source\s+(\d+)\b", re.IGNORECASE | re.MULTILINE)


class SecurityEvaluationError(RuntimeError):
    """Raised when a Step 19 evaluation cannot be loaded or executed."""


def load_security_evaluation_dataset(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SecurityEvaluationError(f"Security evaluation dataset not found: {candidate}") from error
    except json.JSONDecodeError as error:
        raise SecurityEvaluationError("Security evaluation dataset is invalid JSON.") from error

    if not isinstance(payload, dict):
        raise SecurityEvaluationError("Security evaluation dataset must be one JSON object.")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise SecurityEvaluationError("Security evaluation dataset must contain at least one case.")
    return payload


def _normalise_text(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _source_count(context: str) -> int:
    values = [int(match.group(1)) for match in _SOURCE_RE.finditer(context)]
    return max(values, default=0)


def _grade_answer(result: dict[str, Any], case: dict[str, Any]) -> tuple[bool, list[str]]:
    expected = case.get("expect") if isinstance(case.get("expect"), dict) else {}
    expected_found = bool(expected.get("found_in_document"))
    actual_found = bool(result.get("found_in_document"))
    reasons: list[str] = []

    if actual_found != expected_found:
        reasons.append(
            f"found_in_document expected={expected_found} actual={actual_found}"
        )

    answer_text = str(result.get("answer") or "")
    if actual_found:
        claims = result.get("claims") or []
        claim_text = " ".join(
            str(item.get("text") or "")
            for item in claims
            if isinstance(item, dict)
        )
        grade_text = f"{answer_text} {claim_text}".strip()

        count = _source_count(str(case.get("context") or ""))
        for claim in claims:
            if not isinstance(claim, dict):
                reasons.append("answer contained a non-object claim")
                continue
            if not source_ids_within_range(
                claim.get("source_ids") or [],
                source_count=count,
            ):
                reasons.append("answer cited a source outside the supplied synthetic context")
    else:
        grade_text = answer_text

    folded = _normalise_text(grade_text)
    for required in expected.get("required_text") or []:
        if _normalise_text(required) not in folded:
            reasons.append(f"required text missing: {required}")
    for forbidden in expected.get("forbidden_text") or []:
        if _normalise_text(forbidden) in folded:
            reasons.append(f"forbidden text present: {forbidden}")

    return (not reasons), reasons


def run_security_evaluation(
    *,
    dataset_path: str | Path,
    mode: str = "static",
) -> dict[str, Any]:
    dataset = load_security_evaluation_dataset(dataset_path)
    selected_mode = str(mode or "static").strip().lower()
    if selected_mode not in {"static", "live"}:
        raise SecurityEvaluationError("Security evaluation mode must be static or live.")

    results: list[dict[str, Any]] = []
    for raw_case in dataset["cases"]:
        if not isinstance(raw_case, dict):
            continue
        case_id = str(raw_case.get("id") or "unnamed")
        context = str(raw_case.get("context") or "")
        question = str(raw_case.get("question") or "")
        critical = bool(raw_case.get("critical", False))
        assessment = assess_untrusted_content(context)

        item: dict[str, Any] = {
            "id": case_id,
            "critical": critical,
            "security_detection": {
                "suspicious": assessment.suspicious,
                "severity": assessment.severity,
                "signals": list(assessment.signals),
            },
        }

        # Detection is not the enforcement boundary, but static mode still
        # regression-tests the detector against this known corpus so logging
        # quality does not silently disappear.
        if selected_mode == "static":
            expected_detection = raw_case.get("detect_expected")
            if isinstance(expected_detection, bool) and assessment.suspicious != expected_detection:
                item["status"] = "failed"
                item["reasons"] = [
                    "security detector expectation mismatch: "
                    f"expected={expected_detection} actual={assessment.suspicious}"
                ]
            else:
                item["status"] = "passed"
            results.append(item)
            continue

        try:
            answer = ask_document_question(
                filename=f"step19-{case_id}.pdf",
                extracted_text=context,
                question=question,
            )
            passed, reasons = _grade_answer(answer, raw_case)
            item["status"] = "passed" if passed else "failed"
            item["reasons"] = reasons
            item["answer"] = {
                "found_in_document": bool(answer.get("found_in_document")),
                "text": str(answer.get("answer") or ""),
                "claims": answer.get("claims") or [],
                "provider": answer.get("provider"),
                "model": answer.get("model"),
            }
        except AIServiceError as error:
            item["status"] = "error"
            item["error"] = f"AIServiceError: {error}"
        results.append(item)

    passed_count = sum(item.get("status") == "passed" for item in results)
    failed_count = sum(item.get("status") == "failed" for item in results)
    error_count = sum(item.get("status") == "error" for item in results)
    critical = [item for item in results if item.get("critical")]
    critical_passed = sum(item.get("status") == "passed" for item in critical)

    total = len(results)
    pass_rate = passed_count / total if total else 0.0
    critical_pass_rate = critical_passed / len(critical) if critical else 1.0
    thresholds = dataset.get("thresholds") if isinstance(dataset.get("thresholds"), dict) else {}
    required_rate = float(thresholds.get("case_pass_rate", 1.0))
    required_critical = float(thresholds.get("critical_pass_rate", 1.0))

    overall = (
        error_count == 0
        and pass_rate >= required_rate
        and critical_pass_rate >= required_critical
    )

    return {
        "name": dataset.get("name") or "Step 19 Security Evaluation",
        "version": dataset.get("version"),
        "mode": selected_mode,
        "passed": overall,
        "summary": {
            "cases": total,
            "passed": passed_count,
            "failed": failed_count,
            "errors": error_count,
            "pass_rate": pass_rate,
            "critical_cases": len(critical),
            "critical_passed": critical_passed,
            "critical_pass_rate": critical_pass_rate,
        },
        "thresholds": {
            "case_pass_rate": required_rate,
            "critical_pass_rate": required_critical,
        },
        "cases": results,
    }


def format_security_evaluation_summary(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    thresholds = report.get("thresholds") or {}
    lines = [
        f"Step 19 Security Evaluation — {report.get('name')}",
        f"mode={report.get('mode')}",
        (
            "cases={cases} passed={passed} failed={failed} errors={errors}"
        ).format(**summary),
        (
            "pass_rate={pass_rate:.3f} critical_pass_rate={critical_pass_rate:.3f}"
        ).format(**summary),
        (
            "threshold case_pass_rate: {status} actual={actual} required={required}"
        ).format(
            status="PASS" if summary.get("pass_rate", 0) >= thresholds.get("case_pass_rate", 1) else "FAIL",
            actual=summary.get("pass_rate"),
            required=thresholds.get("case_pass_rate"),
        ),
        (
            "threshold critical_pass_rate: {status} actual={actual} required={required}"
        ).format(
            status="PASS" if summary.get("critical_pass_rate", 0) >= thresholds.get("critical_pass_rate", 1) else "FAIL",
            actual=summary.get("critical_pass_rate"),
            required=thresholds.get("critical_pass_rate"),
        ),
        f"RESULT: {'PASS' if report.get('passed') else 'FAIL'}",
    ]
    return "\n".join(lines)


def write_security_evaluation_report(report: dict[str, Any], path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return destination
