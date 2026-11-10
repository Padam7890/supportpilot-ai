"""Claim grounding safety regressions."""

from app.features.ai.application.claim_grounding import check_grounded_claims


def test_rejects_unrecognized_source_index():
    result = check_grounded_claims("Refunds take 7 days [source: 3]", [{"excerpt": "7 days"}])
    assert result.accepted is False
    assert result.reason == "invalid_citation_index"


def test_rejects_unsupported_numeric_policy():
    result = check_grounded_claims("Refunds take 30 days [source: 1]", [{"excerpt": "Refunds take 7 days"}])
    assert result.accepted is False
    assert result.unsupported_numbers == ("30 days",)


def test_accepts_cited_number_present_in_source():
    result = check_grounded_claims("Refunds take 7 days [source: 1]", [{"excerpt": "Refunds take 7 days"}])
    assert result.accepted is True


def test_missing_citation_fails_closed():
    result = check_grounded_claims("Refunds take 7 days", [{"excerpt": "Refunds take 7 days"}])
    assert result.reason == "missing_citations"


def test_empty_sources_fail_closed():
    assert check_grounded_claims("Refunds take 7 days", []).reason == "no_sources"
