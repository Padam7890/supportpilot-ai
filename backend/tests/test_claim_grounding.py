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


def test_cited_source_does_not_borrow_number_from_uncited_source():
    result = check_grounded_claims(
        "Refunds take 30 days [source: 1]",
        [
            {"excerpt": "Refunds take 7 days."},
            {"excerpt": "Shipping may take 30 days."},
        ],
    )
    assert not result.accepted
    assert result.reason == "unsupported_numeric_claim"


def test_numeric_unit_mismatch_is_not_accepted():
    result = check_grounded_claims(
        "Warranty lasts 7 weeks [source 1].", [{"excerpt": "Warranty lasts 7 days."}]
    )
    assert not result.accepted


def test_cited_source_allows_matching_number():
    result = check_grounded_claims(
        "Returns are accepted within 7 days [source: 1].",
        [
            {"excerpt": "Returns are accepted within 7 days."},
            {"excerpt": "Delivery takes 30 days."},
        ],
    )
    assert result.accepted


def test_thousands_separator_is_normalized():
    result = check_grounded_claims(
        "The limit is 1000 units [source 1].",
        [{"excerpt": "The limit is 1,000 units."}],
    )
    assert result.accepted


def test_different_thousands_values_are_rejected():
    result = check_grounded_claims(
        "The limit is 2,000 units [source 1].",
        [{"excerpt": "The limit is 1,000 units."}],
    )
    assert not result.accepted
    assert result.unsupported_numbers == ("2000",)


def test_decimal_values_are_not_confused():
    result = check_grounded_claims(
        "The fee is 2.5% [source 1].", [{"excerpt": "The fee is 2.0%."}]
    )
    assert not result.accepted


def test_numeric_claims_with_citations_use_only_referenced_excerpt():
    result = check_grounded_claims(
        "The warranty lasts 2 years [doc: 2].",
        [
            {"excerpt": "The warranty lasts 2 years."},
            {"excerpt": "The warranty lasts 1 year."},
        ],
    )
    assert not result.accepted


def test_empty_model_answer_is_blocked():
    assert check_grounded_claims("  ", []).reason == "empty_answer"


def test_empty_cited_excerpt_is_blocked():
    result = check_grounded_claims("The policy applies [source: 1].", [{"excerpt": ""}])
    assert not result.accepted
    assert result.reason == "empty_evidence"
