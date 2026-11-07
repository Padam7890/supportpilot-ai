from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.integrations.core.contracts.messaging import IncomingMessage
from app.integrations.messaging.service import (
    MAX_DELIVERY_ATTEMPTS,
    persist_incoming_message,
    retry_delay_seconds,
)


def test_delivery_retry_delay_uses_bounded_full_jitter():
    assert retry_delay_seconds(1, random_value=0.0) == 1
    assert retry_delay_seconds(1, random_value=1.0) == 2
    assert retry_delay_seconds(20, random_value=1.0) == 900


def test_provider_retry_after_is_respected_with_upper_bound():
    assert retry_delay_seconds(3, retry_after_seconds=17) == 17
    assert retry_delay_seconds(3, retry_after_seconds=5000) == 900
    assert retry_delay_seconds(3, retry_after_seconds=0) == 1


def test_retry_policy_rejects_invalid_attempt_and_jitter_values():
    with pytest.raises(ValueError):
        retry_delay_seconds(0)
    with pytest.raises(ValueError):
        retry_delay_seconds(1, random_value=1.1)


def test_delivery_retry_limit_is_bounded():
    assert MAX_DELIVERY_ATTEMPTS == 8


class FakeSession:
    def __init__(self, scalar_results):
        self.scalar_results = list(scalar_results)
        self.inserted_statement = None
        self.loaded_message = SimpleNamespace(id=uuid4())

    async def scalar(self, statement):
        if getattr(statement, "is_insert", False):
            self.inserted_statement = statement
        return self.scalar_results.pop(0)

    async def get(self, model, message_id):
        return self.loaded_message


def incoming_message(organization_id, connection_id):
    return IncomingMessage(
        organization_id=organization_id,
        integration_connection_id=connection_id,
        provider_id="example_chat",
        external_conversation_id="thread-7",
        external_message_id="message-9",
        external_sender_id="external-customer-3",
        content="Hello",
        occurred_at=datetime.now(UTC),
        provider_metadata={"email": "should-not-be-persisted@example.test"},
    )


@pytest.mark.anyio
async def test_normalized_inbound_message_is_tenant_scoped_and_saves_no_provider_pii(monkeypatch):
    async def no_workflow_matches(*_args, **_kwargs):
        return 0

    monkeypatch.setattr(
        "app.integrations.messaging.service.enqueue_customer_message_workflows",
        no_workflow_matches,
    )
    organization_id = uuid4()
    connection_id = uuid4()
    connection = SimpleNamespace(id=connection_id)
    conversation = SimpleNamespace(
        id=uuid4(),
        ticket_id=uuid4(),
        updated_at=datetime.now(UTC),
        external_conversation_id="thread-7",
    )
    session = FakeSession([connection, conversation, uuid4()])

    message, created = await persist_incoming_message(
        session, incoming_message(organization_id, connection_id)
    )

    assert message is session.loaded_message
    assert created is True
    values = session.inserted_statement.compile().params
    assert values["organization_id"] == organization_id
    assert values["conversation_id"] == conversation.id
    assert values["integration_connection_id"] == connection_id
    assert values["external_message_id"] == "message-9"
    assert values["provider_metadata"] == {"provider_id": "example_chat", "attachments": []}


@pytest.mark.anyio
async def test_normalized_inbound_message_rejects_cross_tenant_connection():
    session = FakeSession([None])

    with pytest.raises(ValueError, match="connection is unavailable"):
        await persist_incoming_message(session, incoming_message(uuid4(), uuid4()))
