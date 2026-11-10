"""The complete reply is verified before release and only used citations survive."""

from unittest.mock import AsyncMock, patch

import pytest

from app.features.ai.application.conversation_response_composer import ComposedAnswer
from app.features.ai.application.guarded_generation import generate_guarded_draft
from app.features.ai.application.semantic_claim_verifier import SemanticVerification


def _arguments() -> dict:
    return {
        "execution_id": "test",
        "execution_kind": "playground",
        "question": "What is the refund policy?",
        "instructions": "Keep it brief.",
        "transcript": [],
        "context": [
            {"document_id": "shipping", "chunk_index": 0, "excerpt": "Shipping is free."},
            {"document_id": "returns", "chunk_index": 2, "excerpt": "Returns within 14 days."},
        ],
        "integration_context": {},
        "citations": [
            {"document_id": "shipping", "chunk_index": 0},
            {"document_id": "returns", "chunk_index": 2},
        ],
        "outcomes": [],
        "requires_evidence": True,
        "correlation_id": None,
    }


@pytest.mark.anyio
async def test_verified_reply_remaps_citations_and_counts_review_usage(monkeypatch):
    compose = AsyncMock(return_value=ComposedAnswer("Returns within 14 days [source 2].", {"total_tokens": 5}, None))
    verify = AsyncMock(return_value=SemanticVerification(True, "verified", (2,), {"total_tokens": 4}))
    monkeypatch.setattr("app.features.ai.application.guarded_generation.compose_natural_answer", compose)
    monkeypatch.setattr("app.features.ai.application.guarded_generation.verify_candidate", verify)
    result = await generate_guarded_draft(**_arguments())
    assert result.accepted
    assert result.text == "Returns within 14 days [source 1]."
    assert result.citations == [{"document_id": "returns", "chunk_index": 2}]
    assert result.usage == {"total_tokens": 9}
    assert result.model_name is None
    assert compose.await_args.kwargs["instructions"] == "Keep it brief."


@pytest.mark.anyio
async def test_rejected_semantic_claim_is_never_returned(monkeypatch):
    monkeypatch.setattr(
        "app.features.ai.application.guarded_generation.compose_natural_answer",
        AsyncMock(return_value=ComposedAnswer("All items are refundable [source 2].", {}, "test")),
    )
    monkeypatch.setattr(
        "app.features.ai.application.guarded_generation.verify_candidate",
        AsyncMock(return_value=SemanticVerification(False, "contradicted_claim")),
    )
    result = await generate_guarded_draft(**_arguments())
    assert not result.accepted
    assert result.grounding_reason == "contradicted_claim"
    assert "All items" not in result.text
    assert result.citations == []


@pytest.mark.anyio
async def test_store_question_without_evidence_skips_model():
    with patch(
        "app.features.ai.application.guarded_generation.compose_natural_answer",
        new_callable=AsyncMock,
    ) as compose:
        result = await generate_guarded_draft(**(_arguments() | {"context": [], "citations": []}))
    compose.assert_not_awaited()
    assert not result.accepted
    assert result.grounding_reason == "no_verified_evidence"


@pytest.mark.anyio
async def test_order_snapshot_is_rendered_without_model_calls():
    with patch(
        "app.features.ai.application.guarded_generation.compose_natural_answer",
        new_callable=AsyncMock,
    ) as compose:
        result = await generate_guarded_draft(**(_arguments() | {
            "execution_kind": "reply_draft", "context": [], "citations": [],
            "integration_context": {
                "order_number": "#42", "financial_status": "PAID", "email": "private@example.test",
            },
        }))
    compose.assert_not_awaited()
    assert result.accepted
    assert "#42" in result.text and "paid" in result.text
    assert "private@example.test" not in result.text
