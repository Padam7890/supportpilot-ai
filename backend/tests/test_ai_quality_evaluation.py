"""Offline quality gate: fail CI on safety regression."""
from app.features.ai.application.quality_evaluation import (
    CASES,
    QualityCase,
    evaluate_suite,
)


def test_grounding_quality_suite_has_no_regressions() -> None:
    report = evaluate_suite()
    assert report["total"] >= 7
    assert report["failed"] == 0, report


def test_quality_suite_rejects_duplicate_case_ids() -> None:
    import pytest

    with pytest.raises(ValueError, match="unique"):
        evaluate_suite((CASES[0], CASES[0]))


def test_quality_suite_rejects_empty_suite() -> None:
    import pytest

    with pytest.raises(ValueError, match="empty"):
        evaluate_suite(())


def test_quality_suite_reports_regressions_by_category() -> None:
    broken = QualityCase(
        case_id="broken", category="numeric",
        response="Refunds take 30 days [source: 1]",
        excerpts=("Refunds take 7 days",),
        expected_accepted=True, expected_reason="lexical_checks_passed",
    )
    report = evaluate_suite((broken,))
    assert report["failed"] == 1
    assert report["failed_case_ids"] == ["broken"]
    assert report["by_category"]["numeric"] == {"total": 1, "passed": 0}
