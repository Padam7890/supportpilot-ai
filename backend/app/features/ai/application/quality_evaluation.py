"""Deterministic, offline AI quality regression runner.

No external provider calls, private transcripts, or customer identifiers.
Fixtures are versioned, synthetic and safe to run in CI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.features.ai.application.claim_grounding import check_grounded_claims

QualityCategory = Literal["grounding", "citation", "numeric", "missing_evidence"]


@dataclass(frozen=True)
class QualityCase:
    case_id: str
    category: QualityCategory
    response: str
    excerpts: tuple[str, ...]
    expected_accepted: bool
    expected_reason: str


@dataclass(frozen=True)
class QualityResult:
    case_id: str
    category: QualityCategory
    passed: bool
    actual_accepted: bool
    actual_reason: str


CASES: tuple[QualityCase, ...] = (
    QualityCase("valid-policy", "grounding", "Returns take 7 days [source: 1].",
                ("Returns take 7 days.",), True, "lexical_checks_passed"),
    QualityCase("fabricated-window", "numeric", "Returns take 30 days [source: 1].",
                ("Returns take 7 days.",), False, "unsupported_numeric_claim"),
    QualityCase("invalid-source", "citation", "Returns take 7 days [source: 2].",
                ("Returns take 7 days.",), False, "invalid_citation_index"),
    QualityCase("missing-citation", "citation", "Returns take 7 days.",
                ("Returns take 7 days.",), False, "missing_citations"),
    QualityCase("no-evidence", "missing_evidence", "Returns take 7 days [source: 1].",
                (), False, "no_sources"),
    QualityCase("wrong-units", "numeric", "Warranty lasts 7 weeks [doc: 1].",
                ("Warranty lasts 7 days.",), False, "unsupported_numeric_claim"),
    QualityCase("uncited-source-borrow", "numeric", "Returns take 30 days [source: 1].",
                ("Returns take 7 days.", "Shipping takes 30 days."), False,
                "unsupported_numeric_claim"),
)


def evaluate_case(case: QualityCase) -> QualityResult:
    if not case.case_id or not case.category:
        raise ValueError("Evaluation case requires stable identifiers")
    outcome = check_grounded_claims(
        case.response, [{"excerpt": excerpt} for excerpt in case.excerpts],
        require_citations=True,
    )
    return QualityResult(
        case_id=case.case_id, category=case.category,
        passed=(outcome.accepted == case.expected_accepted
                and outcome.reason == case.expected_reason),
        actual_accepted=outcome.accepted, actual_reason=outcome.reason,
    )


def evaluate_suite(cases: tuple[QualityCase, ...] = CASES) -> dict[str, object]:
    if not cases:
        raise ValueError("Evaluation suite cannot be empty")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Evaluation case IDs must be unique")
    results = [evaluate_case(case) for case in cases]
    failures = [result.case_id for result in results if not result.passed]
    categories = sorted({result.category for result in results})
    return {
        "total": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "failed_case_ids": failures,
        "by_category": {
            category: {
                "total": sum(result.category == category for result in results),
                "passed": sum(result.category == category and result.passed for result in results),
            }
            for category in categories
        },
    }
