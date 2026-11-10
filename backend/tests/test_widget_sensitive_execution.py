"""Sensitive widget routes must never execute order mutations."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.features.ai.application.conversation_orchestration import CustomerTurnPlan
from app.features.ai.application.widget_sensitive_execution import (
    complete_sensitive_widget_turn,
)


@pytest.mark.asyncio
async def test_unverified_cancellation_requests_verification() -> None:
    organization_id, execution_id, conversation_id = uuid4(), uuid4(), uuid4()
    with (
        patch(
            "app.features.ai.application.widget_sensitive_execution.widget_is_cancellation_request",
            return_value=True,
        ),
        patch(
            "app.features.ai.application.widget_sensitive_execution.verified_widget_order_reply",
            new_callable=AsyncMock,
            return_value=(False, None),
        ) as lookup,
        patch(
            "app.features.ai.application.widget_sensitive_execution.finish_widget_reply",
            new_callable=AsyncMock,
        ) as finish,
    ):
        await complete_sensitive_widget_turn(
            organization_id, execution_id, conversation_id,
            question="Cancel my order",
            turn=CustomerTurnPlan(route="sensitive", draft="Please verify", reply_status="escalated"),
            delivery_status="sent",
            outcomes=[],
        )
    lookup.assert_awaited_once()
    assert finish.await_args.kwargs["pending_question"] is not None


@pytest.mark.asyncio
async def test_rejects_non_sensitive_route() -> None:
    with pytest.raises(ValueError):
        await complete_sensitive_widget_turn(
            uuid4(), uuid4(), uuid4(), question="hello",
            turn=CustomerTurnPlan(route="direct"), delivery_status="sent",
            outcomes=[],
        )
