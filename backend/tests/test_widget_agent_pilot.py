"""Feature-flagged widget pilot regression scenarios."""

from unittest.mock import AsyncMock, patch

import pytest

from app.features.ai.application.conversation_agent import AgentRunResult
from app.features.ai.application.widget_agent_pilot import (
    eligible_for_widget_agent_pilot, try_complete_widget_agent_pilot,
)


def test_pilot_is_off_by_default() -> None:
    with patch(
        "app.features.ai.application.widget_agent_pilot.settings.ai_conversation_llm_first_enabled",
        False,
    ):
        assert not eligible_for_widget_agent_pilot("Hello", [])


def test_pilot_excludes_order_and_policy_requests() -> None:
    with patch(
        "app.features.ai.application.widget_agent_pilot.settings.ai_conversation_llm_first_enabled",
        True,
    ):
        assert not eligible_for_widget_agent_pilot("Where is my order?", [])
        assert not eligible_for_widget_agent_pilot("What is your refund policy?", [])


@pytest.mark.asyncio
async def test_pilot_persists_greeting_via_existing_writer() -> None:
    from uuid import uuid4

    organization_id, execution_id, agent_id = uuid4(), uuid4(), uuid4()
    with (
        patch(
            "app.features.ai.application.widget_agent_pilot.settings.ai_conversation_llm_first_enabled",
            True,
        ),
        patch(
            "app.features.ai.application.widget_agent_pilot.widget_reply_is_stale",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "app.features.ai.application.widget_agent_pilot.run_read_only_agent_turn",
            new_callable=AsyncMock,
            return_value=AgentRunResult(
                answer="Hello! How can I help?",
                source_ids=[], tool_names=[], usage={}, model_name="test",
            ),
        ),
        patch(
            "app.features.ai.application.widget_agent_pilot.finish_widget_reply",
            new_callable=AsyncMock,
        ) as persist,
    ):
        completed = await try_complete_widget_agent_pilot(
            organization_id=organization_id,
            execution_id=execution_id,
            ai_agent_id=agent_id,
            message="Hello",
            transcript=[],
            delivery_mode="draft_only",
        )
    assert completed
    assert persist.await_args.kwargs["reply_status"] == "draft_ready"


@pytest.mark.asyncio
async def test_pilot_falls_back_on_invalid_model_plan() -> None:
    from uuid import uuid4

    with (
        patch(
            "app.features.ai.application.widget_agent_pilot.settings.ai_conversation_llm_first_enabled",
            True,
        ),
        patch(
            "app.features.ai.application.widget_agent_pilot.widget_reply_is_stale",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "app.features.ai.application.widget_agent_pilot.run_read_only_agent_turn",
            new_callable=AsyncMock,
            side_effect=ValueError("Invalid agent plan"),
        ),
        patch(
            "app.features.ai.application.widget_agent_pilot.finish_widget_reply",
            new_callable=AsyncMock,
        ) as persist,
    ):
        completed = await try_complete_widget_agent_pilot(
            organization_id=uuid4(),
            execution_id=uuid4(),
            ai_agent_id=uuid4(),
            message="Hello",
            transcript=[],
            delivery_mode="auto_reply",
        )
    assert not completed
    persist.assert_not_awaited()


def test_pilot_rejects_substantive_previous_turns() -> None:
    with patch(
        "app.features.ai.application.widget_agent_pilot.settings.ai_conversation_llm_first_enabled",
        True,
    ):
        assert not eligible_for_widget_agent_pilot(
            "Hello",
            [
                {"sender": "customer", "content": "Where is my order?"},
                {"sender": "assistant", "content": "Please verify your identity."},
            ],
        )


@pytest.mark.asyncio
async def test_pilot_rejects_numeric_output_without_persistence() -> None:
    from uuid import uuid4

    with (
        patch(
            "app.features.ai.application.widget_agent_pilot.settings.ai_conversation_llm_first_enabled",
            True,
        ),
        patch(
            "app.features.ai.application.widget_agent_pilot.widget_reply_is_stale",
            new_callable=AsyncMock, return_value=False,
        ),
        patch(
            "app.features.ai.application.widget_agent_pilot.run_read_only_agent_turn",
            new_callable=AsyncMock,
            return_value=AgentRunResult(
                answer="We have 50 products.", source_ids=[],
                tool_names=[], usage={}, model_name="test",
            ),
        ),
        patch(
            "app.features.ai.application.widget_agent_pilot.finish_widget_reply",
            new_callable=AsyncMock,
        ) as persist,
    ):
        completed = await try_complete_widget_agent_pilot(
            organization_id=uuid4(), execution_id=uuid4(), ai_agent_id=uuid4(),
            message="Hello", transcript=[], delivery_mode="auto_reply",
        )
    assert not completed
    persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_pilot_does_not_persist_reply_if_new_message_arrives_during_generation() -> None:
    from uuid import uuid4

    with (
        patch(
            "app.features.ai.application.widget_agent_pilot.settings.ai_conversation_llm_first_enabled",
            True,
        ),
        patch(
            "app.features.ai.application.widget_agent_pilot.widget_reply_is_stale",
            new_callable=AsyncMock,
            side_effect=[False, True],
        ) as stale,
        patch(
            "app.features.ai.application.widget_agent_pilot.run_read_only_agent_turn",
            new_callable=AsyncMock,
            return_value=AgentRunResult(
                answer="Hello! How can I help?",
                source_ids=[], tool_names=[], usage={}, model_name="test",
            ),
        ),
        patch(
            "app.features.ai.application.widget_agent_pilot.finish_widget_reply",
            new_callable=AsyncMock,
        ) as persist,
    ):
        completed = await try_complete_widget_agent_pilot(
            organization_id=uuid4(),
            execution_id=uuid4(),
            ai_agent_id=uuid4(),
            message="Hello",
            transcript=[],
            delivery_mode="auto_reply",
        )
    assert completed
    assert stale.await_count == 2
    persist.assert_not_awaited()
