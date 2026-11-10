import json
from unittest.mock import AsyncMock

import pytest

from app.features.ai.application.conversation_response_evidence import (
    EvidenceItem,
    ResponseEvidence,
)
from app.features.ai.application.semantic_claim_verifier import verify_candidate

_POLICY = ResponseEvidence(
    (EvidenceItem("knowledge", "Only unused items may be returned within 14 days.", "doc", 0),),
    "verified",
)


def _review(*spans):
    return AsyncMock(return_value=(json.dumps({"spans": list(spans)}), {"total_tokens": 12}, "test"))


@pytest.mark.anyio
@pytest.mark.parametrize("verdict,reason", [
    ("unsupported", "unsupported_claim"),
    ("contradicted", "contradicted_claim"),
    ("ambiguous", "ambiguous_claim"),
    ("sensitive", "sensitive_claim"),
])
async def test_semantic_disagreement_blocks_even_valid_numbers(verdict, reason):
    model = _review({"index": 1, "verdict": verdict, "sources": [1]})
    result = await verify_candidate("Used items may be returned within 14 days [source 1].", _POLICY, review_model=model)
    assert not result.accepted and result.reason == reason


@pytest.mark.anyio
async def test_all_spans_and_citations_are_required():
    model = _review({"index": 1, "verdict": "entailed", "sources": [1]})
    result = await verify_candidate(
        "Unused items may be returned within 14 days [source 1]. Every return is free.",
        _POLICY, review_model=model,
    )
    assert not result.accepted and result.reason == "invalid_review"


@pytest.mark.anyio
async def test_verifier_does_not_override_numeric_unit_check():
    model = _review({"index": 1, "verdict": "entailed", "sources": [1]})
    result = await verify_candidate("Unused items can be returned within 14 weeks [source 1].", _POLICY, review_model=model)
    assert not result.accepted and result.reason == "unsupported_numeric_claim"


@pytest.mark.anyio
async def test_general_response_can_pass_without_evidence():
    model = _review({"index": 1, "verdict": "general", "sources": []})
    result = await verify_candidate("How can I help?", ResponseEvidence(), review_model=model)
    assert result.accepted and result.source_indices == ()


@pytest.mark.anyio
async def test_sensitive_order_assertion_is_blocked_without_contacting_reviewer():
    model = _review({"index": 1, "verdict": "general", "sources": []})
    result = await verify_candidate("Your order #42 was refunded.", ResponseEvidence(), review_model=model)
    assert not result.accepted and result.reason == "sensitive_claim"
    model.assert_not_awaited()


@pytest.mark.anyio
async def test_one_review_recovers_omitted_citations_with_full_coverage():
    model = _review(
        {"index": 4, "verdict": "general", "sources": []},
        {"index": 2, "verdict": "entailed", "sources": [1]},
        {"index": 3, "verdict": "entailed", "sources": [1]},
        {"index": 1, "verdict": "entailed", "sources": [1]},
    )
    result = await verify_candidate(
        r"Only unused items are eligible.\nYou can return unused items within 14 days.\nUsed items are excluded.\nCan I help?",
        _POLICY, review_model=model,
    )
    assert result.accepted and result.source_indices == (1,) and result.citations_recovered == 3
    model.assert_awaited_once()


@pytest.mark.anyio
async def test_invalid_or_mismatched_source_cannot_be_repaired():
    model = _review({"index": 1, "verdict": "entailed", "sources": [1]})
    result = await verify_candidate(
        "Returns are allowed within 14 days [source 2].", _POLICY, review_model=model,
    )
    assert not result.accepted and result.reason == "invalid_citation_index"
    model.assert_awaited_once()
