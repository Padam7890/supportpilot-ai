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


def test_delivery_gate_blocks_unsupported_numeric_claim():
    from app.features.ai.application.claim_grounding import check_generated_answer

    result = check_generated_answer(
        "Refunds take 30 days.", [{"excerpt": "Refunds take 7 days."}]
    )
    assert not result.accepted
    assert result.reason == "unsupported_numeric_claim"


def test_delivery_gate_preserves_existing_uncited_text_without_numbers():
    from app.features.ai.application.claim_grounding import check_generated_answer

    result = check_generated_answer(
        "Please check the returns policy.", [{"excerpt": "Returns policy applies."}]
    )
    assert result.accepted


def test_delivery_gate_rejects_bad_explicit_citation():
    from app.features.ai.application.claim_grounding import check_generated_answer

    result = check_generated_answer(
        "Returns are supported [source: 99].", [{"excerpt": "Returns policy applies."}]
    )
    assert not result.accepted
    assert result.reason == "invalid_citation_index"


def test_stream_segment_rejects_unverified_number():
    from app.features.ai.application.claim_grounding import check_stream_segment

    assert not check_stream_segment(
        "Refund in 30 days.", [{"excerpt": "Refund in 7 days."}]
    ).accepted


def test_stream_segment_rejects_missing_sources():
    from app.features.ai.application.claim_grounding import check_stream_segment

    assert check_stream_segment("Refunds are available.", []).reason == "no_sources"


def test_stream_segment_acceptance_does_not_authorize_delivery():
    from app.features.ai.application.claim_grounding import check_stream_segment

    result = check_stream_segment(
        "Refund in 7 days.", [{"excerpt": "Refund in 7 days."}]
    )
    assert result.accepted
    assert result.reason == "lexical_checks_passed"


def test_cited_source_does_not_borrow_number_from_uncited_source():
    from app.features.ai.application.claim_grounding import check_generated_answer

    result = check_generated_answer(
        "Refunds take 30 days [source: 1]",
        [
            {"excerpt": "Refunds take 7 days."},
            {"excerpt": "Shipping may take 30 days."},
        ],
    )
    assert not result.accepted
    assert result.reason == "unsupported_numeric_claim"


def test_numeric_unit_mismatch_is_not_accepted():
    from app.features.ai.application.claim_grounding import check_generated_answer

    result = check_generated_answer(
        "Warranty lasts 7 weeks.", [{"excerpt": "Warranty lasts 7 days."}]
    )
    assert not result.accepted


def test_cited_source_allows_matching_number():
    from app.features.ai.application.claim_grounding import check_generated_answer

    result = check_generated_answer(
        "Returns are accepted within 7 days [source: 1].",
        [
            {"excerpt": "Returns are accepted within 7 days."},
            {"excerpt": "Delivery takes 30 days."},
        ],
    )
    assert result.accepted


def test_thousands_separator_is_normalized():
    from app.features.ai.application.claim_grounding import check_generated_answer

    result = check_generated_answer(
        "The limit is 1000 units.",
        [{"excerpt": "The limit is 1,000 units."}],
    )
    assert result.accepted


def test_different_thousands_values_are_rejected():
    from app.features.ai.application.claim_grounding import check_generated_answer

    result = check_generated_answer(
        "The limit is 2,000 units.",
        [{"excerpt": "The limit is 1,000 units."}],
    )
    assert not result.accepted
    assert result.unsupported_numbers == ("2000",)


def test_decimal_values_are_not_confused():
    from app.features.ai.application.claim_grounding import check_generated_answer

    result = check_generated_answer(
        "The fee is 2.5%.", [{"excerpt": "The fee is 2.0%."}]
    )
    assert not result.accepted


def test_numeric_claims_with_citations_use_only_referenced_excerpt():
    from app.features.ai.application.claim_grounding import check_generated_answer

    result = check_generated_answer(
        "The warranty lasts 2 years [doc: 2].",
        [
            {"excerpt": "The warranty lasts 2 years."},
            {"excerpt": "The warranty lasts 1 year."},
        ],
    )
    assert not result.accepted
