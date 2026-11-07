import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.core.security import hash_password
from app.db.session import SessionLocal, set_tenant_context
from app.integrations.core import (
    DeliveryReceipt,
    IncomingMessage,
    IntegrationCapability,
    IntegrationError,
    IntegrationErrorCode,
    IntegrationRegistry,
    ProviderDescriptor,
)
from app.integrations.messaging.service import enqueue_outbound_delivery, persist_incoming_message
from app.integrations.messaging.worker import (
    claim_integration_delivery,
    process_integration_delivery,
)
from app.models import (
    AIAgent,
    CatalogWebhookEvent,
    Conversation,
    Customer,
    IntegrationConnection,
    IntegrationDeliveryJob,
    IntegrationWebhookEvent,
    Message,
    PlatformOwner,
    Ticket,
)
from tests.auth_helpers import verify_registration, workspace_login


class FakeMessagingProvider:
    descriptor = ProviderDescriptor(
        provider_id="example_chat",
        display_name="Example chat",
        version="test",
        capabilities=frozenset({IntegrationCapability.OUTBOUND_MESSAGING}),
    )

    def __init__(self):
        self.attempts = 0
        self.idempotency_keys = []

    def get_capability(self, capability):
        return self if capability is IntegrationCapability.OUTBOUND_MESSAGING else None

    async def send_message(self, connection, *, external_conversation_id, message, idempotency_key):
        self.attempts += 1
        self.idempotency_keys.append(idempotency_key)
        if self.attempts == 1:
            raise IntegrationError(IntegrationErrorCode.TRANSIENT_FAILURE, retryable=True)
        return DeliveryReceipt(
            external_message_id="provider-message-1",
            status="sent",
            accepted_at=datetime.now(UTC),
            provider_status="sent",
        )


pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Messaging persistence integration requires isolated PostgreSQL",
)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def approved_owner(client, label: str) -> dict:
    slug = f"{label}-{uuid4().hex[:10]}"
    email = f"{label}-{uuid4().hex[:10]}@example.com"
    password = "messaging-integration-test-password"
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"{label} workspace",
            "organization_slug": slug,
            "full_name": "Integration Owner",
            "email": email,
            "password": password,
        },
    )
    assert registration.status_code == 202, registration.text
    await verify_registration(client, registration, email)
    platform_email = f"platform-{uuid4().hex[:10]}@example.com"
    platform_password = "messaging-platform-integration-password"
    async with SessionLocal() as session:
        session.add(
            PlatformOwner(email=platform_email, password_hash=hash_password(platform_password))
        )
        await session.commit()
    platform_login = await client.post(
        "/api/v1/platform/auth/login",
        json={"email": platform_email, "password": platform_password},
    )
    assert platform_login.status_code == 200, platform_login.text
    platform_token = platform_login.json()["access_token"]
    pending = await client.get(
        "/api/v1/platform/tenants?approval_status=pending", headers=bearer(platform_token)
    )
    tenant = next(item for item in pending.json()["items"] if item["slug"] == slug)
    approval = await client.post(
        f"/api/v1/platform/tenants/{tenant['id']}/approve", headers=bearer(platform_token)
    )
    assert approval.status_code == 200, approval.text
    return await workspace_login(client, email, password, slug)


@pytest.mark.anyio
async def test_inbound_idempotency_tenant_boundaries_and_transactional_outbox(client):
    owner_a = await approved_owner(client, "messages-a")
    owner_b = await approved_owner(client, "messages-b")
    organization_a = UUID(owner_a["user"]["organization_id"])
    organization_b = UUID(owner_b["user"]["organization_id"])

    async with SessionLocal() as session:
        await set_tenant_context(session, organization_a)
        connection = IntegrationConnection(
            organization_id=organization_a,
            provider_id="example_chat",
            external_account_id="account-1",
            display_name="Example chat account",
            status="connected",
            connected_by_user_id=UUID(owner_a["user"]["id"]),
        )
        customer = Customer(
            organization_id=organization_a,
            name="External customer",
            email=f"external-{uuid4().hex[:12]}@example.invalid",
        )
        session.add_all([connection, customer])
        await session.flush()
        ticket = Ticket(
            organization_id=organization_a,
            customer_id=customer.id,
            subject="External conversation",
            description="",
            status="open",
            priority="normal",
            source="integration",
        )
        session.add(ticket)
        await session.flush()
        agent = await session.scalar(select(AIAgent).where(AIAgent.organization_id == organization_a, AIAgent.is_default.is_(True)))
        conversation = Conversation(
            organization_id=organization_a,
            ticket_id=ticket.id,
            channel="example_chat",
            integration_connection_id=connection.id,
            external_conversation_id="thread-1",
            ai_agent_id=agent.id,
        )
        session.add(conversation)
        await session.flush()
        outgoing = Message(
            organization_id=organization_a,
            conversation_id=conversation.id,
            sender_type="agent",
            sender_user_id=UUID(owner_a["user"]["id"]),
            content="We can help with that.",
            content_type="text",
        )
        session.add(outgoing)
        await session.flush()
        first_job = await enqueue_outbound_delivery(
            session,
            organization_id=organization_a,
            connection_id=connection.id,
            message=outgoing,
        )
        retry_job = await enqueue_outbound_delivery(
            session,
            organization_id=organization_a,
            connection_id=connection.id,
            message=outgoing,
        )
        assert first_job.id == retry_job.id
        outbox_job_id = first_job.id

        incoming = IncomingMessage(
            organization_id=organization_a,
            integration_connection_id=connection.id,
            provider_id="example_chat",
            external_conversation_id="thread-1",
            external_message_id="external-message-1",
            external_sender_id="sender-1",
            content="Where is my package?",
            occurred_at=datetime.now(UTC),
            provider_metadata={"email": "private@example.test"},
        )
        inbound, inserted = await persist_incoming_message(session, incoming)
        repeated, inserted_again = await persist_incoming_message(session, incoming)
        assert inserted is True
        assert inserted_again is False
        assert inbound.id == repeated.id
        assert inbound.provider_metadata == {"provider_id": "example_chat", "attachments": []}
        first_contact = IncomingMessage(
            organization_id=organization_a,
            integration_connection_id=connection.id,
            provider_id="example_chat",
            external_conversation_id="first-contact-thread",
            external_message_id="first-contact-message",
            external_sender_id="new-sender",
            sender_display_name="New shopper",
            content="I need help with a product",
            occurred_at=datetime.now(UTC),
        )
        first_contact_message, created = await persist_incoming_message(session, first_contact)
        assert created is True
        first_contact_conversation = await session.get(
            Conversation, first_contact_message.conversation_id
        )
        assert first_contact_conversation is not None
        assert first_contact_conversation.external_conversation_id == "first-contact-thread"
        assert first_contact_conversation.integration_connection_id == connection.id
        assert (
            await session.scalar(
                select(func.count(IntegrationDeliveryJob.id)).where(
                    IntegrationDeliveryJob.organization_id == organization_a,
                    IntegrationDeliveryJob.message_id == outgoing.id,
                )
            )
            == 1
        )
        session.add_all(
            [
                IntegrationWebhookEvent(
                    organization_id=organization_a,
                    connection_id=connection.id,
                    provider_id="example_chat",
                    external_event_id="webhook-event-1",
                    event_type="message.created",
                    occurred_at=datetime.now(UTC),
                    payload_fingerprint="a" * 64,
                    normalized_payload={"customer_email": "private@example.test"},
                ),
                CatalogWebhookEvent(
                    organization_id=organization_a,
                    connection_id=connection.id,
                    provider_id="example_chat",
                    external_event_id="webhook-event-1",
                    event_type="message.created",
                    external_product_id="not-applicable",
                    payload={"private": "must not be returned"},
                    status="failed",
                    attempt_count=2,
                    max_attempts=5,
                    next_attempt_at=datetime.now(UTC),
                    last_error_code="provider_timeout",
                ),
            ]
        )
        connection_id = connection.id
        await session.commit()

    event_response = await client.get(
        f"/api/v1/integrations/connections/{connection_id}/events",
        headers=bearer(owner_a["access_token"]),
    )
    assert event_response.status_code == 200, event_response.text
    event = event_response.json()["items"][0]
    assert event["processing_status"] == "failed"
    assert event["attempt_count"] == 2
    assert event["last_error_code"] == "provider_timeout"
    assert "private@example.test" not in event_response.text
    assert "must not be returned" not in event_response.text

    delivery_response = await client.get(
        f"/api/v1/integrations/connections/{connection_id}/deliveries",
        headers=bearer(owner_a["access_token"]),
    )
    assert delivery_response.status_code == 200, delivery_response.text
    delivery = delivery_response.json()["items"][0]
    assert delivery["id"] == str(outbox_job_id)
    assert delivery["status"] == "queued"
    assert "We can help with that." not in delivery_response.text
    assert delivery_response.json()["total"] == 1

    delivery_analytics = await client.get(
        "/api/v1/analytics/integration-deliveries", headers=bearer(owner_a["access_token"])
    )
    assert delivery_analytics.status_code == 200, delivery_analytics.text
    analytics_body = delivery_analytics.json()
    assert analytics_body["total"] == 1
    assert analytics_body["queued"] == 1
    assert analytics_body["providers"] == [
        {"provider_id": "example_chat", "total": 1, "succeeded": 0, "failed": 0}
    ]
    assert "We can help with that." not in delivery_analytics.text

    isolated_analytics = await client.get(
        "/api/v1/analytics/integration-deliveries", headers=bearer(owner_b["access_token"])
    )
    assert isolated_analytics.status_code == 200, isolated_analytics.text
    assert isolated_analytics.json()["total"] == 0

    hidden_events = await client.get(
        f"/api/v1/integrations/connections/{connection_id}/events",
        headers=bearer(owner_b["access_token"]),
    )
    hidden_deliveries = await client.get(
        f"/api/v1/integrations/connections/{connection_id}/deliveries",
        headers=bearer(owner_b["access_token"]),
    )
    assert hidden_events.status_code == hidden_deliveries.status_code == 404

    messaging_provider = FakeMessagingProvider()
    registry = IntegrationRegistry()
    registry.register(messaging_provider)
    first_claim = await claim_integration_delivery(organization_a)
    assert first_claim == outbox_job_id
    assert await process_integration_delivery(organization_a, first_claim, registry=registry)
    async with SessionLocal() as session:
        await set_tenant_context(session, organization_a)
        retryable_job = await session.get(IntegrationDeliveryJob, outbox_job_id)
        assert retryable_job is not None and retryable_job.status == "queued"
        retryable_job.next_attempt_at = datetime.now(UTC)
        await session.commit()
    second_claim = await claim_integration_delivery(organization_a)
    assert second_claim == outbox_job_id
    assert await process_integration_delivery(organization_a, second_claim, registry=registry)
    assert messaging_provider.attempts == 2
    assert len(set(messaging_provider.idempotency_keys)) == 1
    async with SessionLocal() as session:
        await set_tenant_context(session, organization_a)
        delivered_job = await session.get(IntegrationDeliveryJob, outbox_job_id)
        delivered_message = await session.get(Message, outgoing.id)
        assert delivered_job is not None and delivered_job.status == "succeeded"
        assert delivered_message is not None
        assert delivered_message.delivery_status == "sent"
        assert delivered_message.external_message_id == "provider-message-1"

    cross_tenant_event = IncomingMessage(
        organization_id=organization_b,
        integration_connection_id=connection_id,
        provider_id="example_chat",
        external_conversation_id="thread-1",
        external_message_id="external-message-2",
        external_sender_id="sender-1",
        content="Must not cross tenant boundaries",
        occurred_at=datetime.now(UTC),
    )
    async with SessionLocal() as session:
        await set_tenant_context(session, organization_b)
        with pytest.raises(ValueError, match="connection is unavailable"):
            await persist_incoming_message(session, cross_tenant_event)
        await session.rollback()
