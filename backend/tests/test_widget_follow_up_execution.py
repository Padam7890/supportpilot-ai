"""Refund follow-up completion never issues a refund or bypasses OTP."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.features.ai.application.follow_up import FollowUp, PendingQuestion
from app.features.ai.application.widget_follow_up_execution import (
    complete_widget_follow_up,
)


@pytest.mark.asyncio
async def test_unverified_refund_requires_otp() -> None:
    review = PendingQuestion(
        active_intent="refund",
        stage="refund_verification",
        expected_answer_type="otp",
        refund_reason="damaged",
    )
    with patch(
        "app.features.ai.application.widget_follow_up_execution.finish_widget_reply",
        new_callable=AsyncMock,
    ) as finish:
        result = await complete_widget_follow_up(
            uuid4(), uuid4(), uuid4(),
            follow_up=FollowUp(decision="refund_review", review=review),
            delivery_status="sent",
        )
    assert result.completed is True
    assert result.failure_stage == "refund_verification"
    assert finish.await_args.kwargs["pending_question"].verification_status == "required"


@pytest.mark.asyncio
async def test_unhandled_follow_up_returns_to_normal_router() -> None:
    result = await complete_widget_follow_up(
        uuid4(), uuid4(), uuid4(),
        follow_up=FollowUp(decision="policy_timing", routed_question="delivery policy"),
        delivery_status="sent",
    )
    assert result.completed is False


@pytest.mark.asyncio
async def test_verified_refund_missing_context_raises_instead_of_leaving_job_running() -> None:
    from app.features.ai.application.widget_follow_up_execution import (
        FollowUpRetrievalUnavailable,
    )

    review = PendingQuestion(
        active_intent="refund", stage="refund_verification",
        expected_answer_type="otp", refund_reason="damaged",
        verification_id=uuid4(), item_message_id=uuid4(),
    )
    with (
        patch(
            "app.features.ai.application.widget_follow_up_execution.refund_verification_is_active",
            new_callable=AsyncMock, return_value=True,
        ),
        patch(
            "app.features.ai.application.widget_follow_up_execution.load_execution_context",
            new_callable=AsyncMock, return_value=None,
        ),
        patch(
            "app.features.ai.application.widget_follow_up_execution.finish_widget_reply",
            new_callable=AsyncMock,
        ) as finish,
    ):
        with pytest.raises(FollowUpRetrievalUnavailable):
            await complete_widget_follow_up(
                uuid4(), uuid4(), uuid4(),
                follow_up=FollowUp(decision="refund_review", review=review),
                delivery_status="sent",
            )
    finish.assert_not_awaited()
