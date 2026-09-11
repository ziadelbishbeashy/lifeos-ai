"""Step 19 security-evaluation runner tests without live provider calls."""

import json
from pathlib import Path

from services.security_evaluation_service import (
    format_security_evaluation_summary,
    load_security_evaluation_dataset,
    run_security_evaluation,
    write_security_evaluation_report,
)


def _dataset_path() -> Path:
    return Path(__file__).resolve().parents[1] / "evaluations" / "step19_prompt_injection.json"


def test_step19_dataset_loads_and_contains_critical_attacks():
    dataset = load_security_evaluation_dataset(_dataset_path())
    assert dataset["version"] == 1
    ids = {case["id"] for case in dataset["cases"]}
    assert "direct_override" in ids
    assert "unsupported_hallucination_override" in ids
    assert "table_cell_injection" in ids
    assert sum(bool(case.get("critical")) for case in dataset["cases"]) >= 6


def test_step19_static_security_eval_passes_without_provider_calls(tmp_path):
    report = run_security_evaluation(
        dataset_path=_dataset_path(),
        mode="static",
    )
    assert report["passed"] is True
    assert report["summary"]["errors"] == 0
    assert report["summary"]["critical_pass_rate"] == 1.0

    output = write_security_evaluation_report(report, tmp_path / "step19.json")
    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored["passed"] is True
    assert "RESULT: PASS" in format_security_evaluation_summary(report)
