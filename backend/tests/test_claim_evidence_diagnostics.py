"""Phase 11: lexical candidate matching must never be confused with factual support."""
from app.features.ai.application.claim_evidence_diagnostics import inspect_claim_evidence


def test_no_sources() -> None:
    result = inspect_claim_evidence("Refunds are available in seven days.", [])
    assert result.status == "no_sources"
    assert result.candidate_source_indices == ()


def test_unrelated_source() -> None:
    result = inspect_claim_evidence(
        "Refunds are available in seven days.",
        ["The store opens every morning at nine."],
    )
    assert result.status == "no_lexical_candidate"


def test_overlapping_but_contradictory_source_remains_unverified() -> None:
    result = inspect_claim_evidence(
        "Refunds are available within seven days.",
        ["Refunds are not available within seven days."],
    )
    assert result.status == "lexical_candidate_unverified"
    assert result.candidate_source_indices == (0,)


def test_matches_only_correct_excerpt_index() -> None:
    result = inspect_claim_evidence(
        "Delivery is available in Kathmandu.",
        ["Our refund process takes five days.", "Delivery is unavailable in Kathmandu."],
    )
    assert result.candidate_source_indices == (1,)
    assert result.status == "lexical_candidate_unverified"


def test_rejects_invalid_overlap() -> None:
    import pytest
    with pytest.raises(ValueError):
        inspect_claim_evidence("a", ["a"], minimum_shared_terms=0)
