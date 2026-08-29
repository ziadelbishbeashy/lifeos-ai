"""Pure Step 18 metric contract tests."""

from services.rag_evaluation_metrics import (
    answer_text_checks,
    normalize_answer_text,
    page_matches,
    source_expectation_metrics,
)


def test_step18_answer_normalization_tolerates_number_formatting():
    assert normalize_answer_text("Laptop — 3,250 units") == "laptop - 3250 units"
    result = answer_text_checks(
        answer="Laptop had 3250 units in Q4.",
        required=["3,250", "Laptop"],
    )
    assert result["passed"] is True


def test_step18_page_matching_supports_page_ranges():
    assert page_matches(3, "2-4") is True
    assert page_matches("3", 3) is True
    assert page_matches(7, "2-4") is False


def test_step18_source_metrics_measure_recall_and_mrr():
    actual = [
        {"filename": "other.pdf", "page": 1, "content_type": "text"},
        {"filename": "retail.pdf", "page": 3, "content_type": "table"},
        {"filename": "finance.pdf", "page": 2, "content_type": "text"},
    ]
    metrics = source_expectation_metrics(
        expected_sources=[
            {"filename": "retail.pdf", "page": 3, "content_type": "table"},
            {"filename": "finance.pdf"},
        ],
        actual_sources=actual,
    )
    assert metrics["recall"] == 1.0
    assert metrics["all_expected_found"] is True
    assert metrics["reciprocal_rank"] == 0.5


def test_step18_answer_text_detects_required_and_forbidden_facts():
    result = answer_text_checks(
        answer="The codename is AURORA-26.",
        required=["AURORA-26"],
        forbidden=["CEO salary"],
    )
    assert result["passed"] is True

    failed = answer_text_checks(
        answer="The CEO salary is EGP 8.4 million.",
        forbidden=["EGP 8.4 million"],
    )
    assert failed["passed"] is False
