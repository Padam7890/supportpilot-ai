"""Guarded generation must suppress ungrounded claims before delivery."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.features.ai.application.guarded_generation import generate_guarded_draft


@pytest.mark.asyncio
async def test_rejected_grounding_returns_safe_fallback() -> None:
    with (
        patch(
            "app.features.ai.application.guarded_generation.create_grounded_draft",
            new_callable=AsyncMock,
            return_value={"draft": "Unverified price: 12345", "usage": {}, "model_name": "test"},
        ),
        patch(
            "app.features.ai.application.guarded_generation.check_generated_answer",
            return_value=SimpleNamespace(accepted=False, reason="unsupported_claim"),
        ),
        patch("app.features.ai.application.guarded_generation.log_generation_metrics"),
    ):
        result = await generate_guarded_draft(
            organization_id=uuid4(), execution_id=uuid4(),
            execution_kind="widget_reply", question="price?",
            instructions=None, transcript=[], context=[], integration_context=None,
            citations=[{"source": "test"}], outcomes=[], auto_reply=True,
            correlation_id=None,
        )
    assert result.accepted is False
    assert "12345" not in result.text
    assert result.citations == []
    assert result.outcomes[-1]["status"] == "blocked"


@pytest.mark.asyncio
async def test_accepted_grounding_preserves_sources() -> None:
    citations = [{"source": "approved"}]
    with (
        patch(
            "app.features.ai.application.guarded_generation.create_grounded_draft",
            new_callable=AsyncMock,
            return_value={"draft": "Approved policy answer", "usage": {}, "model_name": "test"},
        ),
        patch(
            "app.features.ai.application.guarded_generation.check_generated_answer",
            return_value=SimpleNamespace(accepted=True, reason=None),
        ),
        patch("app.features.ai.application.guarded_generation.log_generation_metrics"),
    ):
        result = await generate_guarded_draft(
            organization_id=uuid4(), execution_id=uuid4(),
            execution_kind="playground", question="policy?",
            instructions=None, transcript=[], context=[], integration_context=None,
            citations=citations, outcomes=[], auto_reply=False, correlation_id=None,
        )
    assert result.accepted is True
    assert result.text == "Approved policy answer"
    assert result.citations == citations


@pytest.mark.asyncio
async def test_missing_provider_model_name_is_not_stringified() -> None:
    with (
        patch(
            "app.features.ai.application.guarded_generation.create_grounded_draft",
            new_callable=AsyncMock,
            return_value={"draft": "Hello", "usage": {}, "model_name": None},
        ),
        patch(
            "app.features.ai.application.guarded_generation.check_generated_answer",
            return_value=SimpleNamespace(accepted=True, reason=None),
        ),
        patch("app.features.ai.application.guarded_generation.log_generation_metrics"),
    ):
        result = await generate_guarded_draft(
            organization_id=uuid4(), execution_id=uuid4(),
            execution_kind="playground", question="hello", instructions=None,
            transcript=[], context=[], integration_context=None,
            citations=[], outcomes=[], auto_reply=False, correlation_id=None,
        )
    assert result.model_name is None
