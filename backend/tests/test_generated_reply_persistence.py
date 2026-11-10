"""Generated reply persistence guards tenant, agent and source authorization."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.features.ai.application.generated_reply_persistence import (
    complete_non_widget_generated_reply,
)
from app.features.ai.application.guarded_generation import GuardedDraft


def _guarded() -> GuardedDraft:
    return GuardedDraft(
        text="Verified response", accepted=True, grounding_reason=None,
        citations=[{"id": "source"}], outcomes=[], usage={"total_tokens": 12},
        model_name="test",
    )


@pytest.mark.asyncio
async def test_missing_or_non_running_execution_is_not_modified() -> None:
    db = AsyncMock()
    db.scalar.return_value = None
    session = AsyncMock()
    session.__aenter__.return_value = db
    with (
        patch(
            "app.features.ai.application.generated_reply_persistence.SessionLocal",
            return_value=session,
        ),
        patch(
            "app.features.ai.application.generated_reply_persistence.set_tenant_context",
            new_callable=AsyncMock,
        ),
    ):
        await complete_non_widget_generated_reply(
            uuid4(), uuid4(), guarded=_guarded(), completed_at=datetime.now(UTC)
        )
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_deactivated_agent_suppresses_generated_answer() -> None:
    row = SimpleNamespace(
        ai_agent_id=uuid4(), kind="playground", status="running",
        integration_context_encrypted="encrypted", playground_history=[],
        draft=None, safe_summary=None, citations=[], error_code=None,
        completed_at=None,
    )
    db = AsyncMock()
    db.scalar.side_effect = [row, None]
    session = AsyncMock()
    session.__aenter__.return_value = db
    with (
        patch(
            "app.features.ai.application.generated_reply_persistence.SessionLocal",
            return_value=session,
        ),
        patch(
            "app.features.ai.application.generated_reply_persistence.set_tenant_context",
            new_callable=AsyncMock,
        ),
    ):
        await complete_non_widget_generated_reply(
            uuid4(), uuid4(), guarded=_guarded(), completed_at=datetime.now(UTC)
        )
    assert row.status == "succeeded"
    assert row.draft != "Verified response"
    assert row.citations == []
    db.commit.assert_awaited_once()
