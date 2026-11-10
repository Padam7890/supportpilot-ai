import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from typing import ClassVar
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal, set_tenant_context
from app.features.widgets.retention import purge_expired_order_verifications
from app.models import (
    AIAgent,
    AIExecution,
    Conversation,
    DocumentChunk,
    IntegrationConnection,
    KnowledgeBase,
    KnowledgeDocument,
    Message,
    PlatformOwner,
    SupportWidget,
    Ticket,
    WidgetOrderVerification,
    WidgetSubmission,
)
from app.services import ai_worker
from app.services.ai_worker import claim_ai_execution, finish_widget_reply, process_ai_execution
from tests.auth_helpers import verify_registration, workspace_login

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Storefront widget integration tests require isolated PostgreSQL",
)


@pytest.mark.anyio
async def test_expired_order_verification_cleanup_is_bounded_and_tenant_scoped(client):
    _auth_a, organization_a, public_id_a = await setup_widget(
        client, "widget-retention-a", "https://retention-a.example"
    )
    _auth_b, organization_b, public_id_b = await setup_widget(
        client, "widget-retention-b", "https://retention-b.example"
    )

    async def create_conversation(public_id: str, origin: str) -> tuple[UUID, UUID]:
        created = await client.post(
            f"/api/v1/widget/{public_id}/messages",
            headers={"Origin": origin, "Idempotency-Key": f"retention-{uuid4().hex}"},
            json={"content": "Need order help"},
        )
        assert created.status_code == 201, created.text
        return UUID(created.json()["conversation_id"]), UUID(created.json()["ticket_id"])

    conversation_a, _ticket_a = await create_conversation(
        public_id_a, "https://retention-a.example"
    )
    conversation_b, _ticket_b = await create_conversation(
        public_id_b, "https://retention-b.example"
    )
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        for organization_id, public_id, conversation_id, suffix in (
            (organization_a, public_id_a, conversation_a, "a-old"),
            (organization_b, public_id_b, conversation_b, "b-old"),
        ):
            await set_tenant_context(db, organization_id)
            widget = await db.scalar(
                select(SupportWidget).where(
                    SupportWidget.organization_id == organization_id,
                    SupportWidget.public_id == public_id,
                )
            )
            assert widget is not None
            db.add(
                WidgetOrderVerification(
                    organization_id=organization_id,
                    widget_id=widget.id,
                    conversation_id=conversation_id,
                    order_number="#1001",
                    shopify_order_id="gid://shopify/Order/1001",
                    customer_email_encrypted="encrypted-email",
                    code_digest="a" * 64,
                    status="verified",
                    attempt_count=0,
                    expires_at=now - timedelta(days=2),
                    verified_at=now - timedelta(days=2),
                )
            )
            if organization_id == organization_a:
                db.add(
                    WidgetOrderVerification(
                        organization_id=organization_a,
                        widget_id=widget.id,
                        conversation_id=conversation_a,
                        order_number="#1002",
                        shopify_order_id="gid://shopify/Order/1002",
                        customer_email_encrypted="encrypted-recent-email",
                        code_digest="b" * 64,
                        status="expired",
                        attempt_count=0,
                        expires_at=now - timedelta(minutes=30),
                    )
                )
            await db.flush()
        await db.commit()

    assert await purge_expired_order_verifications(organization_a) == 1
    assert await purge_expired_order_verifications(organization_b) == 1
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_a)
        remaining = list(
            await db.scalars(
                select(WidgetOrderVerification).where(
                    WidgetOrderVerification.organization_id == organization_a
                )
            )
        )
        assert len(remaining) == 1
        assert remaining[0].order_number == "#1002"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def approved_workspace(client, label: str):
    suffix = uuid4().hex[:10]
    slug = f"{label}-{suffix}"
    email = f"{label}-{suffix}@example.com"
    password = "widget-owner-test-password"
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"{label.title()} Workspace",
            "organization_slug": slug,
            "full_name": "Widget Workspace Owner",
            "email": email,
            "password": password,
        },
    )
    assert registration.status_code == 202, registration.text
    await verify_registration(client, registration, email)

    platform_email = f"platform-{suffix}@example.com"
    platform_password = "widget-platform-test-password"
    async with SessionLocal() as db:
        db.add(PlatformOwner(email=platform_email, password_hash=hash_password(platform_password)))
        await db.commit()
    platform_login = await client.post(
        "/api/v1/platform/auth/login",
        json={"email": platform_email, "password": platform_password},
    )
    pending = await client.get(
        "/api/v1/platform/tenants?approval_status=pending",
        headers=bearer(platform_login.json()["access_token"]),
    )
    tenant_id = next(item["id"] for item in pending.json()["items"] if item["slug"] == slug)
    approved = await client.post(
        f"/api/v1/platform/tenants/{tenant_id}/approve",
        headers=bearer(platform_login.json()["access_token"]),
    )
    assert approved.status_code == 200, approved.text
    login = await workspace_login(client, email, password, slug)
    return login, UUID(tenant_id)


async def setup_widget(
    client, label: str, origin: str, *, ai_enabled: bool = False, ai_reply_mode: str = "draft_only"
):
    auth, organization_id = await approved_workspace(client, label)
    created = await client.post(
        "/api/v1/integrations/widget",
        headers=bearer(auth["access_token"]),
        json={
            "allowed_origins": [origin],
            "collect_contact": True,
            "ai_enabled": ai_enabled,
            "ai_reply_mode": ai_reply_mode,
        },
    )
    assert created.status_code == 201, created.text
    return auth, organization_id, created.json()["public_id"]


@pytest.mark.anyio
async def test_widget_creates_ticket_once_and_reuses_same_visitor_conversation(client):
    _auth, organization_id, public_id = await setup_widget(
        client, "widget-one", "https://store-one.example"
    )
    origin = {"Origin": "https://store-one.example"}
    first = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={**origin, "Idempotency-Key": "first-widget-message-key-01"},
        json={
            "content": "Where is order 1001?",
            "visitor_email": "shopper@example.com",
            "contact_consent": True,
        },
    )
    assert first.status_code == 201, first.text
    started = first.json()
    duplicate = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={**origin, "Idempotency-Key": "first-widget-message-key-01"},
        json={
            "content": "Where is order 1001?",
            "visitor_email": "shopper@example.com",
            "contact_consent": True,
        },
    )
    assert duplicate.status_code == 201, duplicate.text
    assert duplicate.json()["ticket_id"] == started["ticket_id"]
    assert duplicate.json()["conversation_id"] == started["conversation_id"]

    headers = {
        **origin,
        "Authorization": f"Bearer {started['visitor_token']}",
        "Idempotency-Key": "followup-widget-message-01",
    }
    following = await client.post(
        f"/api/v1/widget/conversations/{started['conversation_id']}/messages",
        headers=headers,
        json={"content": "It has not arrived yet."},
    )
    assert following.status_code == 200, following.text
    repeated = await client.post(
        f"/api/v1/widget/conversations/{started['conversation_id']}/messages",
        headers=headers,
        json={"content": "It has not arrived yet."},
    )
    assert repeated.status_code == 200
    assert repeated.json()["id"] == following.json()["id"]
    history = await client.get(
        f"/api/v1/widget/conversations/{started['conversation_id']}",
        headers={**origin, "Authorization": f"Bearer {started['visitor_token']}"},
    )
    assert history.status_code == 200
    assert [row["content"] for row in history.json()["messages"]] == [
        "Where is order 1001?",
        "It has not arrived yet.",
    ]

    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        tickets = list(
            await db.scalars(select(Ticket).where(Ticket.organization_id == organization_id))
        )
        conversations = list(
            await db.scalars(
                select(Conversation).where(Conversation.organization_id == organization_id)
            )
        )
        messages = list(
            await db.scalars(select(Message).where(Message.organization_id == organization_id))
        )
        executions = list(
            await db.scalars(
                select(AIExecution).where(AIExecution.organization_id == organization_id)
            )
        )
        receipts = list(
            await db.scalars(
                select(WidgetSubmission).where(WidgetSubmission.organization_id == organization_id)
            )
        )
        assert len(tickets) == len(conversations) == len(receipts) == 1
        assert tickets[0].source == "shopify_widget"
        assert tickets[0].status == "open"
        assert conversations[0].channel == "shopify_widget"
        assert len(messages) == 2
        assert executions == []
        assert receipts[0].contact_consent is True


@pytest.mark.anyio
async def test_widget_ai_setting_enqueues_one_execution_per_new_message(client):
    _auth, organization_id, public_id = await setup_widget(
        client,
        "widget-ai",
        "https://store-ai.example",
        ai_enabled=True,
        ai_reply_mode="auto_reply",
    )
    headers = {
        "Origin": "https://store-ai.example",
        "Idempotency-Key": "widget-ai-first-message-01",
    }
    first = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers=headers,
        json={"content": "What are your opening hours?"},
    )
    assert first.status_code == 201, first.text
    duplicate = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers=headers,
        json={"content": "What are your opening hours?"},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["conversation_id"] == first.json()["conversation_id"]
    next_message = await client.post(
        f"/api/v1/widget/conversations/{first.json()['conversation_id']}/messages",
        headers={
            "Origin": "https://store-ai.example",
            "Authorization": f"Bearer {first.json()['visitor_token']}",
            "Idempotency-Key": "widget-ai-followup-message-1",
        },
        json={"content": "Are you open on Sunday?"},
    )
    assert next_message.status_code == 200, next_message.text
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        executions = list(
            await db.scalars(
                select(AIExecution).where(
                    AIExecution.organization_id == organization_id,
                    AIExecution.kind == "widget_reply",
                )
            )
        )
        assert len(executions) == 2
        assert all(row.delivery_mode == "auto_reply" for row in executions)
        assert all(row.reply_status == "processing" for row in executions)


@pytest.mark.anyio
async def test_widget_variant_comparison_accepts_only_variants_from_latest_recommendations(client):
    _auth, organization_id, public_id = await setup_widget(
        client, "widget-variant-compare", "https://store-variant-compare.example", ai_enabled=True
    )
    origin = "https://store-variant-compare.example"
    first = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={"Origin": origin, "Idempotency-Key": "widget-variant-start-0001"},
        json={"content": "Show phones"},
    )
    assert first.status_code == 201, first.text
    product_ids = [uuid4(), uuid4()]
    option_ids = [[uuid4(), uuid4()], [uuid4()]]
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        conversation = await db.get(Conversation, first.json()["conversation_id"])
        assert conversation is not None
        conversation.shopping_state = {
            "active": True,
            "last_displayed_recommendations": [
                {
                    "product_id": str(product_id),
                    "variant_id": str(options[0]),
                    "available_variant_ids": [str(option_id) for option_id in options],
                }
                for product_id, options in zip(product_ids, option_ids, strict=True)
            ],
        }
        conversation.shopping_state_expires_at = datetime.now(UTC) + timedelta(days=1)
        await db.commit()

    headers = {
        "Origin": origin,
        "Authorization": f"Bearer {first.json()['visitor_token']}",
        "Idempotency-Key": "widget-variant-compare-valid",
    }
    valid = await client.post(
        f"/api/v1/widget/conversations/{first.json()['conversation_id']}/messages",
        headers=headers,
        json={
            "content": "Compare the first two products",
            "recommendation_selections": [
                {"product_id": str(product_ids[0]), "variant_id": str(option_ids[0][1])},
                {"product_id": str(product_ids[1]), "variant_id": str(option_ids[1][0])},
            ],
        },
    )
    assert valid.status_code == 200, valid.text
    invalid = await client.post(
        f"/api/v1/widget/conversations/{first.json()['conversation_id']}/messages",
        headers={**headers, "Idempotency-Key": "widget-variant-compare-invalid"},
        json={
            "content": "Compare the first two products",
            "recommendation_selections": [
                {"product_id": str(uuid4()), "variant_id": str(uuid4())},
                {"product_id": str(product_ids[1]), "variant_id": str(option_ids[1][0])},
            ],
        },
    )
    assert invalid.status_code == 422
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        saved = await db.scalar(
            select(Message).where(
                Message.organization_id == organization_id,
                Message.conversation_id == first.json()["conversation_id"],
                Message.content == "Compare the first two products",
            )
        )
        assert saved is not None
        assert len(saved.provider_metadata["recommendation_selections"]) == 2


@pytest.mark.anyio
async def test_widget_ai_mode_can_be_overridden_per_conversation(client):
    auth, organization_id, public_id = await setup_widget(
        client,
        "widget-ai-mode",
        "https://store-ai-mode.example",
        ai_enabled=True,
        ai_reply_mode="auto_reply",
    )
    origin = "https://store-ai-mode.example"
    first = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={"Origin": origin, "Idempotency-Key": "widget-ai-mode-first-message"},
        json={"content": "Hello"},
    )
    assert first.status_code == 201, first.text
    conversation_id = first.json()["conversation_id"]
    headers = bearer(auth["access_token"])

    paused = await client.patch(
        f"/api/v1/conversations/{conversation_id}/ai-mode",
        headers=headers,
        json={"mode": "human"},
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["ai_mode"] == "human"

    followup = await client.post(
        f"/api/v1/widget/conversations/{conversation_id}/messages",
        headers={
            "Origin": origin,
            "Authorization": f"Bearer {first.json()['visitor_token']}",
            "Idempotency-Key": "widget-ai-mode-human-followup",
        },
        json={"content": "I need a person"},
    )
    assert followup.status_code == 200, followup.text
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        executions = list(
            await db.scalars(
                select(AIExecution).where(
                    AIExecution.organization_id == organization_id,
                    AIExecution.kind == "widget_reply",
                )
            )
        )
        assert len(executions) == 1

    resumed = await client.patch(
        f"/api/v1/conversations/{conversation_id}/ai-mode",
        headers=headers,
        json={"mode": "ai"},
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["ai_mode"] == "ai"
    resumed_message = await client.post(
        f"/api/v1/widget/conversations/{conversation_id}/messages",
        headers={
            "Origin": origin,
            "Authorization": f"Bearer {first.json()['visitor_token']}",
            "Idempotency-Key": "widget-ai-mode-resumed-followup",
        },
        json={"content": "One more question"},
    )
    assert resumed_message.status_code == 200, resumed_message.text
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        executions = list(
            await db.scalars(
                select(AIExecution).where(
                    AIExecution.organization_id == organization_id,
                    AIExecution.kind == "widget_reply",
                )
            )
        )
        assert len(executions) == 2


class WidgetMockProviderResponse:
    is_error = False

    def __init__(self, content):
        self.content = content

    def json(self):
        return {
            "choices": [{"message": {"content": self.content}}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 8, "total_tokens": 38},
        }


class WidgetMockProviderClient:
    last_payload: ClassVar[dict | None] = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, *, headers, json):
        assert url.endswith("/chat/completions")
        assert "authorization" not in headers
        type(self).last_payload = json
        if json["messages"][0]["content"].startswith("Audit the candidate"):
            return WidgetMockProviderResponse('{"spans":[{"index":1,"verdict":"entailed","sources":[1]}]}')
        return WidgetMockProviderResponse("Our delivery fee is five dollars.")


@pytest.mark.anyio
async def test_widget_draft_only_saves_grounded_result_without_sending(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_intent_router_enabled", False)
    monkeypatch.setattr(settings, "ai_embedding_model", None)
    auth, organization_id, public_id = await setup_widget(
        client, "widget-draft-ai", "https://store-draft-ai.example", ai_enabled=True
    )
    user_id = UUID(auth["user"]["id"])
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        base = await db.scalar(select(KnowledgeBase).where(KnowledgeBase.organization_id == organization_id, KnowledgeBase.is_default.is_(True)))
        from tests.rag_fixtures import hash_chunk_text, hash_document_text

        delivery_policy = "Our delivery charges are five dollars per order."
        document = KnowledgeDocument(
            organization_id=organization_id,
            name="delivery-policy.txt",
            content_type="text/plain",
            size_bytes=40,
            status="ready",
            uploaded_by_user_id=user_id,
            knowledge_base_id=base.id,
            content_revision=hash_document_text(delivery_policy),
        )
        db.add(document)
        await db.flush()
        db.add(
            DocumentChunk(
                organization_id=organization_id,
                document_id=document.id,
                chunk_index=0,
                content=delivery_policy,
                content_hash=hash_chunk_text(delivery_policy),
            )
        )
        await db.commit()
    monkeypatch.setattr(settings, "ai_provider_base_url", "http://127.0.0.1:8012/v1")
    monkeypatch.setattr(settings, "ai_model", "widget-test-model")
    monkeypatch.setattr(settings, "ai_provider_api_key", None)
    monkeypatch.setattr(httpx, "AsyncClient", WidgetMockProviderClient)
    origin = "https://store-draft-ai.example"
    started = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={"Origin": origin, "Idempotency-Key": "widget-draft-ai-message-001"},
        json={"content": "What are your delivery charges?"},
    )
    assert started.status_code == 201, started.text
    organization_execution = await claim_ai_execution(organization_id)
    assert organization_execution is not None
    await process_ai_execution(organization_id, organization_execution)
    status_response = await client.get(
        f"/api/v1/ai/conversations/{started.json()['conversation_id']}/widget-reply",
        headers=bearer(auth["access_token"]),
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "draft_ready"
    assert status_response.json()["draft"] == "Our delivery fee is five dollars."
    assert status_response.json()["citations"]
    history = await client.get(
        f"/api/v1/widget/conversations/{started.json()['conversation_id']}",
        headers={"Origin": origin, "Authorization": f"Bearer {started.json()['visitor_token']}"},
    )
    assert [message["sender_type"] for message in history.json()["messages"]] == ["customer"]


@pytest.mark.anyio
async def test_widget_uses_server_configured_bot_for_conversation_and_execution(client):
    auth, organization_id, public_id = await setup_widget(
        client,
        "widget-selected-bot",
        "https://store-selected-bot.example",
        ai_enabled=True,
    )
    headers = bearer(auth["access_token"])
    default_bases = await client.get("/api/v1/knowledge/bases", headers=headers)
    assert default_bases.status_code == 200, default_bases.text
    default_base_id = default_bases.json()["items"][0]["id"]
    shipping_base = await client.post(
        "/api/v1/knowledge/bases", headers=headers, json={"name": "Shipping"}
    )
    assert shipping_base.status_code == 201, shipping_base.text
    selected = await client.post(
        "/api/v1/ai/agents",
        headers=headers,
        json={"name": "Storefront specialist", "knowledge_base_ids": [default_base_id]},
    )
    assert selected.status_code == 201, selected.text
    selected_agent_id = selected.json()["id"]
    second_selected = await client.post(
        "/api/v1/ai/agents",
        headers=headers,
        json={
            "name": "Shipping specialist",
            "knowledge_base_ids": [shipping_base.json()["id"]],
        },
    )
    assert second_selected.status_code == 201, second_selected.text
    second_agent_id = second_selected.json()["id"]

    config_body = {
        "allowed_origins": ["https://store-selected-bot.example"],
        "enabled": True,
        "collect_contact": True,
        "ai_enabled": True,
        "ai_reply_mode": "draft_only",
        "ai_agent_id": selected_agent_id,
        "ai_agent_ids": [selected_agent_id, second_agent_id],
    }
    configured = await client.put(
        "/api/v1/integrations/widget", headers=headers, json=config_body
    )
    assert configured.status_code == 200, configured.text
    assert configured.json()["ai_agent_id"] == selected_agent_id
    assert configured.json()["ai_agent_ids"] == [selected_agent_id, second_agent_id]
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        from tests.rag_fixtures import hash_chunk_text, hash_document_text

        shipping_faq = "Delivery tracking and parcel courier shipment information."
        document = KnowledgeDocument(
            organization_id=organization_id,
            knowledge_base_id=UUID(shipping_base.json()["id"]),
            name="shipping-faq.txt",
            content_type="text/plain",
            size_bytes=58,
            status="ready",
            uploaded_by_user_id=UUID(auth["user"]["id"]),
            content_revision=hash_document_text(shipping_faq),
        )
        db.add(document)
        await db.flush()
        db.add(
            DocumentChunk(
                organization_id=organization_id,
                document_id=document.id,
                chunk_index=0,
                content=shipping_faq,
                content_hash=hash_chunk_text(shipping_faq),
            )
        )
        await db.commit()

    other_auth, _other_organization_id, _other_widget = await setup_widget(
        client, "widget-other-bot-tenant", "https://other-selected-bot.example"
    )
    other_agents = await client.get(
        "/api/v1/ai/agents", headers=bearer(other_auth["access_token"])
    )
    foreign_agent_id = other_agents.json()["items"][0]["id"]
    cross_tenant_config = await client.put(
        "/api/v1/integrations/widget",
        headers=headers,
        json={**config_body, "ai_agent_ids": [selected_agent_id, foreign_agent_id]},
    )
    assert cross_tenant_config.status_code == 404

    origin = "https://store-selected-bot.example"
    public_config = await client.get(
        f"/api/v1/widget/{public_id}/config", headers={"Origin": origin}
    )
    assert public_config.status_code == 200, public_config.text
    assert "ai_agent_id" not in public_config.json()
    assert "system_instructions" not in public_config.json()

    visitor_supplied_bot = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={"Origin": origin, "Idempotency-Key": "visitor-selected-bot-0001"},
        json={"content": "Hello", "ai_agent_id": foreign_agent_id},
    )
    assert visitor_supplied_bot.status_code == 422

    started = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={"Origin": origin, "Idempotency-Key": "visitor-selected-bot-0002"},
        json={"content": "Hello, I need some help."},
    )
    assert started.status_code == 201, started.text
    conversation_id = UUID(started.json()["conversation_id"])
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        conversation = await db.scalar(
            select(Conversation).where(
                Conversation.organization_id == organization_id,
                Conversation.id == conversation_id,
            )
        )
        execution = await db.scalar(
            select(AIExecution).where(
                AIExecution.organization_id == organization_id,
                AIExecution.conversation_id == conversation_id,
                AIExecution.kind == "widget_reply",
            )
        )
        selected_agent = await db.scalar(
            select(AIAgent).where(
                AIAgent.organization_id == organization_id,
                AIAgent.id == UUID(selected_agent_id),
            )
        )
        assert conversation is not None and str(conversation.ai_agent_id) == selected_agent_id
        assert execution is not None and str(execution.ai_agent_id) == selected_agent_id
        assert selected_agent is not None
        assert execution.ai_agent_config_version == selected_agent.config_version

    continued = await client.post(
        f"/api/v1/widget/conversations/{conversation_id}/messages",
        headers={
            "Origin": origin,
            "Authorization": f"Bearer {started.json()['visitor_token']}",
            "Idempotency-Key": "visitor-shipping-question-0001",
        },
        json={"content": "Where is my shipment tracking?"},
    )
    assert continued.status_code == 200, continued.text
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        conversation = await db.scalar(
            select(Conversation).where(
                Conversation.organization_id == organization_id,
                Conversation.id == conversation_id,
            )
        )
        routed_execution = await db.scalar(
            select(AIExecution)
            .where(
                AIExecution.organization_id == organization_id,
                AIExecution.conversation_id == conversation_id,
                AIExecution.source_message_id == continued.json()["id"],
            )
        )
        assert conversation is not None and str(conversation.ai_agent_id) == second_agent_id
        assert routed_execution is not None and str(routed_execution.ai_agent_id) == second_agent_id


@pytest.mark.anyio
async def test_widget_human_takeover_during_generation_prevents_late_ai_reply(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_intent_router_enabled", False)
    monkeypatch.setattr(settings, "ai_embedding_model", None)
    auth, organization_id, public_id = await setup_widget(
        client,
        "widget-concurrent-takeover",
        "https://store-concurrent-takeover.example",
        ai_enabled=True,
        ai_reply_mode="auto_reply",
    )
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        base = await db.scalar(select(KnowledgeBase).where(KnowledgeBase.organization_id == organization_id, KnowledgeBase.is_default.is_(True)))
        from tests.rag_fixtures import hash_chunk_text, hash_document_text

        returns_copy = "The blue item is made from cotton fabric."
        document = KnowledgeDocument(
            organization_id=organization_id,
            name="returns.txt",
            content_type="text/plain",
            size_bytes=32,
            status="ready",
            uploaded_by_user_id=UUID(auth["user"]["id"]),
            knowledge_base_id=base.id,
            content_revision=hash_document_text(returns_copy),
        )
        db.add(document)
        await db.flush()
        db.add(
            DocumentChunk(
                organization_id=organization_id,
                document_id=document.id,
                chunk_index=0,
                content=returns_copy,
                content_hash=hash_chunk_text(returns_copy),
            )
        )
        await db.commit()

    started_generation = asyncio.Event()
    finish_generation = asyncio.Event()

    async def delayed_generation(**_kwargs):
        started_generation.set()
        await finish_generation.wait()
        from app.features.ai.application.guarded_generation import GuardedDraft

        return GuardedDraft(
            "You can return this within thirty days.", True, None, [], [], {"total_tokens": 4}, "test-model",
        )

    monkeypatch.setattr(ai_worker, "generate_guarded_draft", delayed_generation)
    monkeypatch.setattr(ai_worker, "provider_configuration_error", lambda: None)
    origin = "https://store-concurrent-takeover.example"
    started = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={"Origin": origin, "Idempotency-Key": "widget-takeover-during-ai-01"},
        json={"content": "What material is the blue item made from?"},
    )
    assert started.status_code == 201, started.text
    execution_id = await claim_ai_execution(organization_id)
    assert execution_id is not None

    task = asyncio.create_task(process_ai_execution(organization_id, execution_id))
    await asyncio.wait_for(started_generation.wait(), timeout=2)
    takeover = await client.patch(
        f"/api/v1/conversations/{started.json()['conversation_id']}/ai-mode",
        headers=bearer(auth["access_token"]),
        json={"mode": "human"},
    )
    assert takeover.status_code == 200, takeover.text
    finish_generation.set()
    await asyncio.wait_for(task, timeout=5)

    history = await client.get(
        f"/api/v1/widget/conversations/{started.json()['conversation_id']}",
        headers={
            "Origin": origin,
            "Authorization": f"Bearer {started.json()['visitor_token']}",
        },
    )
    assert [message["sender_type"] for message in history.json()["messages"]] == ["customer"]
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        execution = await db.scalar(
            select(AIExecution).where(
                AIExecution.organization_id == organization_id,
                AIExecution.id == execution_id,
            )
        )
        assert execution.reply_status == "escalated"
        assert execution.draft is None


@pytest.mark.anyio
async def test_widget_sensitive_auto_reply_escalates_without_model_call(client, monkeypatch):
    auth, organization_id, public_id = await setup_widget(
        client,
        "widget-sensitive-ai",
        "https://store-sensitive-ai.example",
        ai_enabled=True,
        ai_reply_mode="auto_reply",
    )
    monkeypatch.setattr(httpx, "AsyncClient", WidgetMockProviderClient)
    WidgetMockProviderClient.last_payload = None
    origin = "https://store-sensitive-ai.example"
    started = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={"Origin": origin, "Idempotency-Key": "widget-sensitive-ai-message-01"},
        json={"content": "Where is my order #1001?"},
    )
    assert started.status_code == 201, started.text
    execution_id = await claim_ai_execution(organization_id)
    assert execution_id is not None
    await process_ai_execution(organization_id, execution_id)
    status_response = await client.get(
        f"/api/v1/ai/conversations/{started.json()['conversation_id']}/widget-reply",
        headers=bearer(auth["access_token"]),
    )
    assert status_response.json()["status"] == "escalated"
    assert WidgetMockProviderClient.last_payload is None
    history = await client.get(
        f"/api/v1/widget/conversations/{started.json()['conversation_id']}",
        headers={"Origin": origin, "Authorization": f"Bearer {started.json()['visitor_token']}"},
    )
    assert [message["sender_type"] for message in history.json()["messages"]] == [
        "customer",
        "assistant",
    ]
    assert "one-time code" in history.json()["messages"][-1]["content"]


@pytest.mark.anyio
async def test_widget_auto_reply_answers_standalone_greeting_without_knowledge_or_model(
    client, monkeypatch
):
    auth, organization_id, public_id = await setup_widget(
        client,
        "widget-greeting-ai",
        "https://store-greeting-ai.example",
        ai_enabled=True,
        ai_reply_mode="auto_reply",
    )

    async def unexpected_model_call(*args, **kwargs):
        raise AssertionError("standalone greeting should not call the model")

    monkeypatch.setattr("app.services.ai_worker.generate_guarded_draft", unexpected_model_call)
    origin = "https://store-greeting-ai.example"
    started = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={"Origin": origin, "Idempotency-Key": "widget-greeting-ai-message-01"},
        json={"content": "hey"},
    )
    assert started.status_code == 201, started.text
    execution_id = await claim_ai_execution(organization_id)
    assert execution_id is not None
    await process_ai_execution(organization_id, execution_id)

    status_response = await client.get(
        f"/api/v1/ai/conversations/{started.json()['conversation_id']}/widget-reply",
        headers=bearer(auth["access_token"]),
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "sent"
    history = await client.get(
        f"/api/v1/widget/conversations/{started.json()['conversation_id']}",
        headers={"Origin": origin, "Authorization": f"Bearer {started.json()['visitor_token']}"},
    )
    assert [message["sender_type"] for message in history.json()["messages"]] == [
        "customer",
        "assistant",
    ]
    assert history.json()["messages"][-1]["content"] == (
        "Hi there! I’m your store’s support assistant. I can help with order updates, product questions, "
        "and store policies. What can I help you with?"
    )


@pytest.mark.anyio
async def test_widget_ai_reply_is_bound_to_one_execution_and_retry_is_idempotent(client):
    _auth, organization_id, public_id = await setup_widget(
        client,
        "widget-reply-idempotency",
        "https://store-reply-idempotency.example",
        ai_enabled=True,
        ai_reply_mode="auto_reply",
    )
    origin = "https://store-reply-idempotency.example"
    started = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={"Origin": origin, "Idempotency-Key": "widget-reply-idempotency-0001"},
        json={"content": "hello"},
    )
    assert started.status_code == 201, started.text
    execution_id = await claim_ai_execution(organization_id)
    assert execution_id is not None
    await process_ai_execution(organization_id, execution_id)

    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        reply_count = await db.scalar(
            select(func.count(Message.id)).where(
                Message.organization_id == organization_id,
                Message.source_ai_execution_id == execution_id,
            )
        )
    assert reply_count == 1

    # Replaying a completed worker execution must not append another assistant row.
    await finish_widget_reply(
        organization_id,
        execution_id,
        draft="duplicate should not persist",
        reply_status="sent",
        safe_summary="Retry regression test.",
        citations=[],
        outcomes=[],
        usage={},
        model_name=None,
    )
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        reply_count = await db.scalar(
            select(func.count(Message.id)).where(
                Message.organization_id == organization_id,
                Message.source_ai_execution_id == execution_id,
            )
        )
    assert reply_count == 1


@pytest.mark.anyio
async def test_widget_origin_honeypot_and_visitor_token_are_enforced(client):
    _auth, _organization_id, public_id = await setup_widget(
        client, "widget-guard", "https://store-allowed.example"
    )
    denied_origin = await client.get(
        f"/api/v1/widget/{public_id}/config",
        headers={"Origin": "https://attacker.example"},
    )
    assert denied_origin.status_code == 403
    spam = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={
            "Origin": "https://store-allowed.example",
            "Idempotency-Key": "honeypot-message-key-0001",
        },
        json={"content": "This is spam", "website": "spam.example"},
    )
    assert spam.status_code == 422
    unauthenticated = await client.get(
        f"/api/v1/widget/conversations/{uuid4()}",
        headers={"Origin": "https://store-allowed.example"},
    )
    assert unauthenticated.status_code == 401


@pytest.mark.anyio
async def test_widget_visitor_token_cannot_access_another_tenant_conversation(client):
    origin = {"Origin": "https://shared-storefront.example"}
    _auth_a, _org_a, widget_a = await setup_widget(client, "tenant-a", origin["Origin"])
    _auth_b, _org_b, widget_b = await setup_widget(client, "tenant-b", origin["Origin"])
    first_a = await client.post(
        f"/api/v1/widget/{widget_a}/messages",
        headers={**origin, "Idempotency-Key": "tenant-a-message-key-0001"},
        json={"content": "Question for tenant A"},
    )
    first_b = await client.post(
        f"/api/v1/widget/{widget_b}/messages",
        headers={**origin, "Idempotency-Key": "tenant-b-message-key-0001"},
        json={"content": "Question for tenant B"},
    )
    assert first_a.status_code == first_b.status_code == 201
    denied = await client.get(
        f"/api/v1/widget/conversations/{first_b.json()['conversation_id']}",
        headers={**origin, "Authorization": f"Bearer {first_a.json()['visitor_token']}"},
    )
    assert denied.status_code == 403


@pytest.mark.anyio
async def test_widget_order_lookup_requires_email_code_and_returns_only_verified_tracking(
    client, monkeypatch
):
    _auth, organization_id, public_id = await setup_widget(
        client,
        "widget-order-otp",
        "https://store-order-otp.example",
        ai_enabled=True,
        ai_reply_mode="auto_reply",
    )
    monkeypatch.setattr("app.features.widgets.order_actions.smtp_is_configured", lambda: True)
    monkeypatch.setattr(
        "app.features.widgets.order_actions.encrypt_credential", lambda value: f"encrypted:{value}"
    )
    monkeypatch.setattr(
        "app.features.widgets.order_actions.decrypt_credential",
        lambda value: value.removeprefix("encrypted:"),
    )
    monkeypatch.setattr(
        "app.features.widgets.cancellation.decrypt_credential",
        lambda value: value.removeprefix("encrypted:"),
    )
    monkeypatch.setattr(
        "app.integrations.providers.shopify.security.decrypt_credential",
        lambda value: value.removeprefix("encrypted:"),
    )

    async def get_installation(db, org_id):
        return _installation()

    monkeypatch.setattr("app.features.widgets.order_actions.installation_for", get_installation)
    monkeypatch.setattr(
        "app.features.widgets.order_actions.valid_access_token", lambda db, installation: _token()
    )
    captured = {}

    async def send_code(email, code):
        captured.update(email=email, code=code)

    async def find_order(*, shop_domain, access_token, order_number, customer_email):
        assert shop_domain == "verified-store.myshopify.com"
        assert access_token == "mock-token"
        assert order_number == "#1001"
        assert customer_email == "shopper@example.com"
        return {
            "id": "gid://shopify/Order/1001",
            "name": "#1001",
            "createdAt": "2026-10-30T12:00:00Z",
            "displayFinancialStatus": "PAID",
            "displayFulfillmentStatus": "FULFILLED",
            "currentTotalPriceSet": {"shopMoney": {"amount": "42.50", "currencyCode": "USD"}},
            "fulfillments": [
                {
                    "trackingInfo": [
                        {
                            "company": "Parcel Co",
                            "number": "TRACK-1001",
                            "url": "https://tracking.example/1001",
                        }
                    ]
                }
            ],
        }

    async def _send(email, code):
        return await send_code(email, code)

    monkeypatch.setattr("app.features.widgets.order_actions.send_order_verification_code", _send)
    monkeypatch.setattr("app.features.widgets.order_actions.lookup_authorized_order", find_order)
    origin = "https://store-order-otp.example"
    started = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={"Origin": origin, "Idempotency-Key": "widget-order-otp-message-1"},
        json={"content": "Where is my order?"},
    )
    assert started.status_code == 201, started.text
    visitor_headers = {
        "Origin": origin,
        "Authorization": f"Bearer {started.json()['visitor_token']}",
    }
    initial_execution = await claim_ai_execution(organization_id)
    assert initial_execution is not None
    await process_ai_execution(organization_id, initial_execution)
    request_code = await client.post(
        f"/api/v1/widget/conversations/{started.json()['conversation_id']}/order-verification",
        headers=visitor_headers,
        json={"order_number": "#1001", "email": "shopper@example.com", "consent": True},
    )
    assert request_code.status_code == 202, request_code.text
    assert "sent to its checkout email" in request_code.json()["message"]
    assert captured["email"] == "shopper@example.com"
    confirmed = await client.post(
        f"/api/v1/widget/conversations/{started.json()['conversation_id']}/order-verification/confirm",
        headers=visitor_headers,
        json={"code": captured["code"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["verified"] is True
    assert confirmed.json()["tracking"][0]["number"] == "TRACK-1001"
    assert "https://tracking.example/1001" in confirmed.json()["message"]
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        db.add(
            IntegrationConnection(
                organization_id=organization_id,
                provider_id="shopify",
                external_account_id="verified-store.myshopify.com",
                display_name="verified-store.myshopify.com",
                status="connected",
                connected_by_user_id=UUID(_auth["user"]["id"]),
            )
        )
        await db.commit()

    class MockCommerceCapability:
        async def lookup_order(self, _connection_ref, *, order_number, verified_customer_email):
            order = await find_order(
                shop_domain="verified-store.myshopify.com",
                access_token="mock-token",
                order_number=order_number,
                customer_email=verified_customer_email,
            )
            return {
                "id": order["id"],
                "order_number": order["name"],
                "created_at": order["createdAt"],
                "financial_status": order["displayFinancialStatus"],
                "fulfillment_status": order["displayFulfillmentStatus"],
                "total_amount": order["currentTotalPriceSet"]["shopMoney"]["amount"],
                "currency": order["currentTotalPriceSet"]["shopMoney"]["currencyCode"],
                "tracking": order["fulfillments"][0]["trackingInfo"],
            }

    class MockProviderRegistry:
        def get_capability(self, *_args):
            return MockCommerceCapability()

    monkeypatch.setattr(
        "app.features.ai.application.widget_orders.build_integration_registry",
        MockProviderRegistry,
    )
    followup = await client.post(
        f"/api/v1/widget/conversations/{started.json()['conversation_id']}/messages",
        headers={**visitor_headers, "Idempotency-Key": "widget-order-followup-status-1"},
        json={"content": "What is my order status?"},
    )
    assert followup.status_code == 200, followup.text
    followup_execution = await claim_ai_execution(organization_id)
    assert followup_execution is not None
    await process_ai_execution(organization_id, followup_execution)
    history_after_followup = await client.get(
        f"/api/v1/widget/conversations/{started.json()['conversation_id']}",
        headers=visitor_headers,
    )
    assert history_after_followup.status_code == 200
    assert history_after_followup.json()["messages"][-1]["content"].startswith(
        "I checked your verified order #1001."
    )
    conversation_after_verification = await client.get(
        f"/api/v1/widget/conversations/{started.json()['conversation_id']}",
        headers=visitor_headers,
    )
    assert conversation_after_verification.status_code == 200
    assert conversation_after_verification.json()["order_verified"] is True
    monkeypatch.setattr("app.features.widgets.cancellation.installation_for", get_installation)
    monkeypatch.setattr(
        "app.features.widgets.cancellation.valid_access_token", lambda db, installation: _token()
    )
    monkeypatch.setattr("app.features.widgets.cancellation.lookup_authorized_order", find_order)
    cancellation = await client.post(
        f"/api/v1/widget/conversations/{started.json()['conversation_id']}/cancellation-request",
        headers={**visitor_headers, "Idempotency-Key": "widget-cancel-order-0001"},
        json={"reason": "I no longer need this order"},
    )
    assert cancellation.status_code == 202, cancellation.text
    assert "must review" in cancellation.json()["message"]
    actions = await client.get("/api/v1/commerce/actions", headers=bearer(_auth["access_token"]))
    assert actions.status_code == 200, actions.text
    assert actions.json()["total"] == 1
    assert actions.json()["items"][0]["approval_status"] == "pending"
    assert actions.json()["items"][0]["execution_status"] == "not_started"
    assert actions.json()["items"][0]["requested_by_name"] == "Customer via storefront chat"


@pytest.mark.anyio
async def test_widget_email_failure_expires_otp_without_losing_tenant_context(client, monkeypatch):
    _auth, organization_id, public_id = await setup_widget(
        client, "widget-otp-email-failure", "https://store-otp-failure.example", ai_enabled=True
    )
    monkeypatch.setattr("app.features.widgets.order_actions.smtp_is_configured", lambda: True)
    monkeypatch.setattr(
        "app.features.widgets.order_actions.encrypt_credential", lambda value: f"encrypted:{value}"
    )

    async def get_installation(db, org_id):
        return _installation()

    async def find_order(**kwargs):
        return {"id": "gid://shopify/Order/2002", "name": "#2002"}

    async def fail_email(email, code):
        raise OSError("mock SMTP failure")

    monkeypatch.setattr("app.features.widgets.order_actions.installation_for", get_installation)
    monkeypatch.setattr(
        "app.features.widgets.order_actions.valid_access_token", lambda db, installation: _token()
    )
    monkeypatch.setattr("app.features.widgets.order_actions.lookup_authorized_order", find_order)
    monkeypatch.setattr(
        "app.features.widgets.order_actions.send_order_verification_code", fail_email
    )

    origin = "https://store-otp-failure.example"
    started = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={"Origin": origin, "Idempotency-Key": "widget-otp-failure-message-1"},
        json={"content": "Where is my order?"},
    )
    assert started.status_code == 201, started.text
    response = await client.post(
        f"/api/v1/widget/conversations/{started.json()['conversation_id']}/order-verification",
        headers={
            "Origin": origin,
            "Authorization": f"Bearer {started.json()['visitor_token']}",
        },
        json={"order_number": "#2002", "email": "shopper@example.com", "consent": True},
    )
    assert response.status_code == 503

    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        verification = await db.scalar(
            select(WidgetOrderVerification).where(
                WidgetOrderVerification.organization_id == organization_id,
                WidgetOrderVerification.conversation_id == UUID(started.json()["conversation_id"]),
            )
        )
        assert verification is not None
        assert verification.status == "expired"


def _installation():
    from types import SimpleNamespace

    return SimpleNamespace(
        shop_domain="verified-store.myshopify.com",
        granted_scopes=["read_orders", "read_customers", "write_orders"],
    )


async def _token():
    return "mock-token"


@pytest.mark.anyio
async def test_reply_stream_rechecks_handoff_before_releasing_more_deltas(client, monkeypatch):
    from contextlib import aclosing
    from types import SimpleNamespace

    from starlette.requests import Request

    from app.features.widgets.reply_stream import reply_events

    monkeypatch.setattr(settings, "widget_ai_streaming_enabled", True)
    origin = "https://store-stream.example"
    _, organization_id, public_id = await setup_widget(
        client, "widget-stream", origin, ai_enabled=True, ai_reply_mode="auto_reply"
    )
    started = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={"Origin": origin, "Idempotency-Key": f"stream-{uuid4().hex}"},
        json={"content": "What is your shipping policy?"},
    )
    assert started.status_code == 201, started.text
    conversation_id = UUID(started.json()["conversation_id"])
    execution_id = await claim_ai_execution(organization_id)
    assert execution_id is not None

    class DeltaStore:
        async def xread(self, streams, *, count, block):
            key, cursor = next(iter(streams.items()))
            assert str(organization_id) in key and str(conversation_id) in key
            assert count > 0 and block > 0
            if cursor == "123-1":
                return []
            assert cursor == "0-0"
            documents = str(uuid4())
            return [(key, [
                ("123-0", {"text": "Shipping ", "documents": documents}),
                ("123-1", {"text": "takes ", "documents": documents}),
            ])]

    async def authorized_sources(*_args, **_kwargs):
        return True

    monkeypatch.setattr(
        "app.features.widgets.reply_stream.citations_remain_authorized", authorized_sources
    )
    async def receive():
        await asyncio.Event().wait()

    request = Request({
        "type": "http",
        "headers": [(b"origin", origin.encode())],
        "app": SimpleNamespace(state=SimpleNamespace(redis=DeltaStore())),
    }, receive)
    authorization = f"Bearer {started.json()['visitor_token']}"
    async with aclosing(reply_events(request, conversation_id, authorization, execution_id, "")) as events:
        assert "event: execution.started" in await anext(events)
        first = await anext(events)
        second = await anext(events)
        assert "event: message.delta" in first and '"text":"Shipping "' in first
        assert "event: message.delta" in second and '"text":"takes "' in second
        assert ":123-0" in first and ":123-1" in second
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            conversation = await db.get(Conversation, conversation_id)
            assert conversation is not None
            conversation.ai_mode = "human"
            await db.commit()
        assert "event: conversation.handoff" in await anext(events)
        with pytest.raises(StopAsyncIteration):
            await anext(events)


@pytest.mark.anyio
async def test_widget_refund_follow_up_persists_through_otp_and_hands_off(client, monkeypatch):
    origin = "https://store-refund-otp.example"
    _, organization_id, public_id = await setup_widget(
        client, "widget-refund-otp", origin, ai_enabled=True, ai_reply_mode="auto_reply",
    )
    from unittest.mock import AsyncMock

    from app.features.ai.application.intent_routing.schemas import RoutingDecision

    router = AsyncMock(return_value=(RoutingDecision.model_validate({
        "intents": [{"intent": "knowledge", "confidence": 0.99, "requires_knowledge": False, "requires_tools": False}],
        "reason_code": "refund_item",
        "follow_up": {"relation": "answer_to_question", "goal": "refund_item", "confidence": 0.99},
    }), {}, None, None))
    monkeypatch.setattr("app.features.ai.application.intent_routing.service.invoke_llm_intent_router", router)
    captured = {}

    async def send_code(_email, code):
        captured["code"] = code

    async def installation_for(_db, _organization_id):
        return _installation()

    async def find_order(**_kwargs):
        return {
            "id": "gid://shopify/Order/1001",
            "name": "#1001",
            "createdAt": "2026-10-30T12:00:00Z",
            "currentTotalPriceSet": {"shopMoney": {"amount": "25.00", "currencyCode": "USD"}},
        }

    for name, replacement in {
        "smtp_is_configured": lambda: True,
        "encrypt_credential": lambda value: value,
        "decrypt_credential": lambda value: value,
        "installation_for": installation_for,
        "valid_access_token": lambda _db, _installation: _token(),
        "lookup_authorized_order": find_order,
        "send_order_verification_code": send_code,
    }.items():
        monkeypatch.setattr(f"app.features.widgets.order_actions.{name}", replacement)

    async def work():
        execution_id = await claim_ai_execution(organization_id)
        assert execution_id is not None
        await process_ai_execution(organization_id, execution_id)
        return execution_id

    started = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={"Origin": origin, "Idempotency-Key": f"refund-{uuid4().hex}"},
        json={"content": "I want a refund."},
    )
    assert started.status_code == 201, started.text
    conversation_url = f"/api/v1/widget/conversations/{started.json()['conversation_id']}"
    headers = {"Origin": origin, "Authorization": f"Bearer {started.json()['visitor_token']}"}

    async def history():
        response = await client.get(conversation_url, headers=headers)
        assert response.status_code == 200, response.text
        return response.json()["messages"]

    async def send(content):
        response = await client.post(
            f"{conversation_url}/messages",
            headers={**headers, "Idempotency-Key": f"refund-{uuid4().hex}"},
            json={"content": content},
        )
        assert response.status_code == 200, response.text
        return await work()

    await work()
    assert "Was the item damaged" in (await history())[-1]["content"]
    await send("damaged")
    assert "Which item was it?" in (await history())[-1]["content"]
    await send("Two blue mugs")
    router.assert_awaited_once()
    assert (await history())[-1]["verification_required"] is True
    await send("yes")
    assert (await history())[-1]["verification_required"] is True

    requested = await client.post(
        f"{conversation_url}/order-verification",
        headers=headers,
        json={"order_number": "#1001", "email": "shopper@example.com", "consent": True},
    )
    assert requested.status_code == 202, requested.text
    verified = await client.post(
        f"{conversation_url}/order-verification/confirm",
        headers=headers,
        json={"code": captured["code"]},
    )
    assert verified.status_code == 200, verified.text
    assert "send this refund request" in (await history())[-1]["content"]
    execution_id = await send("yes")
    assert "No refund has been issued" in (await history())[-1]["content"]
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        execution = await db.get(AIExecution, execution_id)
        assert execution is not None and execution.reply_status == "escalated"


@pytest.mark.anyio
async def test_widget_forgotten_order_number_pauses_verification_and_offers_handoff(client, monkeypatch):
    origin = "https://store-missing-reference.example"
    _, organization_id, public_id = await setup_widget(
        client, "widget-missing-reference", origin, ai_enabled=True, ai_reply_mode="auto_reply",
    )

    async def unexpected_lookup(*_args, **_kwargs):
        pytest.fail("A shopper's missing order reference must not start a Shopify lookup")

    monkeypatch.setattr(ai_worker, "verified_widget_order_reply", unexpected_lookup)

    async def work():
        execution_id = await claim_ai_execution(organization_id)
        assert execution_id is not None
        await process_ai_execution(organization_id, execution_id)
        return execution_id

    started = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={"Origin": origin, "Idempotency-Key": f"missing-ref-{uuid4().hex}"},
        json={"content": "I forget the order number"},
    )
    assert started.status_code == 201, started.text
    conversation_url = f"/api/v1/widget/conversations/{started.json()['conversation_id']}"
    headers = {"Origin": origin, "Authorization": f"Bearer {started.json()['visitor_token']}"}

    async def last_reply():
        history = await client.get(conversation_url, headers=headers)
        assert history.status_code == 200, history.text
        assert history.json()["order_verified"] is False
        return history.json()["messages"][-1]

    async def send(content):
        response = await client.post(
            f"{conversation_url}/messages",
            headers={**headers, "Idempotency-Key": f"missing-ref-{uuid4().hex}"},
            json={"content": content},
        )
        assert response.status_code == 200, response.text
        return await work()

    await work()
    assert (await last_reply())["verification_paused"] is True
    await send("sorry i forget number")
    repeated = await last_reply()
    assert repeated["verification_paused"] is True and repeated["verification_required"] is False
    assert "support team" in repeated["content"]
    assert "Enter the order number" not in repeated["content"]
    escalation_id = await send("yes")
    assert "passed this conversation" in (await last_reply())["content"]
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        execution = await db.get(AIExecution, escalation_id)
        assert execution is not None and execution.reply_status == "escalated"
    await send("Actually, I found it")
    resumed = await last_reply()
    assert resumed["verification_paused"] is False and resumed["verification_required"] is True


@pytest.mark.anyio
async def test_widget_policy_conversation_retrieves_fresh_evidence_per_turn(client, monkeypatch, caplog):
    """Real API, persistence and retrieval with a scripted HTTP model provider."""
    import logging

    from app.features.ai.application.follow_up import PENDING_KEY, PendingQuestion
    from tests.rag_fixtures import hash_chunk_text, hash_document_text

    origin = "https://policy-conversation.example"
    auth, organization_id, public_id = await setup_widget(
        client, f"policy-follow-up-{uuid4().hex[:8]}", origin,
        ai_enabled=True, ai_reply_mode="auto_reply",
    )
    policy = (
        "Damaged products: report the issue within seven days of delivery. "
        "The store team reviews requests for a replacement for damaged products. "
        "For damaged products, include a photo when contacting the store team."
    )
    shipping = "The store offers free standard shipping."
    document_ids = []
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        base = await db.scalar(select(KnowledgeBase).where(
            KnowledgeBase.organization_id == organization_id, KnowledgeBase.is_default.is_(True),
        ))
        for name, content in (("damaged-product-policy.txt", policy), ("shipping-policy.txt", shipping)):
            document = KnowledgeDocument(
                organization_id=organization_id, name=name, content_type="text/plain",
                size_bytes=len(content), status="ready", uploaded_by_user_id=UUID(auth["user"]["id"]),
                knowledge_base_id=base.id, content_revision=hash_document_text(content),
            )
            db.add(document)
            await db.flush()
            document_ids.append(str(document.id))
            db.add(DocumentChunk(
                organization_id=organization_id, document_id=document.id, chunk_index=0,
                content=content, content_hash=hash_chunk_text(content),
            ))
        await db.commit()

    submitted_date = datetime.now(UTC).date() - timedelta(days=10)
    replies = [
        ("You are a helpful", {
            "text": "Report damaged products within seven days of delivery [source 1]. When did the package reach you?",
            "expected_answer": "delivery_date",
        }),
        ("Audit the candidate", {"spans": [
            {"index": 1, "verdict": "entailed", "sources": [1]},
            {"index": 2, "verdict": "general", "sources": []},
        ]}),
        ("You classify", {
            "intents": [{"intent": "knowledge", "confidence": 0.98, "requires_knowledge": True, "requires_tools": False}],
            "reason_code": "contextual_policy",
            "follow_up": {
                "relation": "answer_to_question", "goal": "delivery_date",
                "date_text": f"{submitted_date:%d %b %Y}", "confidence": 0.99,
            },
        }),
        ("Extract the explicit", {"rule": {
            "source": 1, "quote": "Damaged products: report the issue within seven days of delivery.",
            "subject": "reporting damaged products", "measure": "seven days", "start_event": "delivery",
            "conditions": [], "exclusions": [],
        }}),
        ("Audit the candidate", {"spans": [{"index": 1, "verdict": "entailed", "sources": [1]}]}),
    ]
    for goal, reply in (
        ("replacement", "The store team reviews replacement requests for damaged products [source 1]."),
        ("next_step", "Include a photo of the damaged products when you contact the store team [source 1]."),
    ):
        replies.extend([
            ("You classify", {
                "intents": [{"intent": "knowledge", "confidence": 0.98, "requires_knowledge": True, "requires_tools": False}],
                "requires_context": True, "reason_code": "contextual_policy",
                "follow_up": {"relation": "follow_up", "goal": goal, "confidence": 0.99},
            }),
            ("You are a helpful", reply),
            ("Audit the candidate", {"spans": [{"index": 1, "verdict": "entailed", "sources": [1]}]}),
        ])
    replies.extend([
        ("You are a helpful", "The store offers free standard shipping [source 1]."),
        ("Audit the candidate", {"spans": [{"index": 1, "verdict": "entailed", "sources": [1]}]}),
    ])
    calls = []

    class Provider(WidgetMockProviderClient):
        async def post(self, url, *, headers, json):
            expected, response = replies[len(calls)]
            messages = json["messages"]
            assert messages[0]["content"].startswith(expected), messages[0]["content"][:85]
            calls.append(messages)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": response if isinstance(response, str) else dumps(response)}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
                "model": "policy-test-model",
            })

    dumps = json.dumps
    monkeypatch.setattr(settings, "ai_provider_base_url", "http://127.0.0.1:8012/v1")
    monkeypatch.setattr(settings, "ai_model", "policy-test-model")
    monkeypatch.setattr(settings, "ai_provider_api_key", None)
    monkeypatch.setattr(settings, "ai_embedding_model", None)
    monkeypatch.setattr(settings, "ai_intent_router_enabled", False)
    monkeypatch.setattr(settings, "ai_conversation_llm_first_enabled", False)
    monkeypatch.setattr(httpx, "AsyncClient", Provider)
    caplog.set_level(logging.INFO, logger="app.services.ai_worker")
    started = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={"Origin": origin, "Idempotency-Key": "policy-start-0001"},
        json={"content": "My product arrived damaged."},
    )
    assert started.status_code == 201, started.text
    conversation_id = started.json()["conversation_id"]
    headers = {"Origin": origin, "Authorization": f"Bearer {started.json()['visitor_token']}"}
    path = f"/api/v1/widget/conversations/{conversation_id}"
    for index, (message, phrase, source, model_calls) in enumerate((
        (None, "When did the package reach you?", 0, 2),
        (f"{submitted_date:%d %b %Y} is the delivery date.", "estimated deadline around", 0, 3),
        ("I want a replacement.", "reviews replacement requests", 0, 3),
        ("What should I do next?", "Include a photo", 0, 3),
        ("Actually, what is your shipping policy?", "free standard shipping", 1, 2),
    )):
        if message:
            response = await client.post(
                f"{path}/messages",
                headers={**headers, "Idempotency-Key": f"policy-follow-up-{index}"},
                json={"content": message},
            )
            assert response.status_code == 200, response.text
        before = len(calls)
        execution_id = await claim_ai_execution(organization_id)
        assert execution_id
        await process_ai_execution(organization_id, execution_id)
        await process_ai_execution(organization_id, execution_id)
        assert len(calls) - before == model_calls
        history = await client.get(path, headers=headers)
        assistant = [item for item in history.json()["messages"] if item["sender_type"] == "assistant"]
        assert len(assistant) == index + 1
        assert phrase in assistant[-1]["content"]
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            execution = await db.get(AIExecution, execution_id)
            assert execution and execution.status == "succeeded" and execution.reply_status == "sent"
            assert execution.error_code is None
            assert execution.usage["total_tokens"] >= 140
            assert [str(c["document_id"]) for c in execution.citations] == [document_ids[source]]
            if index in {1, 2, 3}:
                row = await db.scalar(select(Message).where(Message.source_ai_execution_id == execution_id))
                state = PendingQuestion.model_validate(row.provider_metadata[PENDING_KEY]).policy_context
                assert state and state.delivery_date.normalized == submitted_date
    assert len(calls) == 13
    assert "ai_execution_model_budget" in caplog.text
