import os
from typing import ClassVar
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal, set_tenant_context
from app.models import (
    AIExecution,
    Conversation,
    DocumentChunk,
    KnowledgeDocument,
    Message,
    PlatformOwner,
    Ticket,
    WidgetOrderVerification,
    WidgetSubmission,
)
from app.services.ai_worker import claim_ai_execution, process_ai_execution

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Storefront widget integration tests require isolated PostgreSQL",
)


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
    login = await client.post(
        "/api/v1/auth/login",
        json={"organization_slug": slug, "email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return login.json(), UUID(tenant_id)


async def setup_widget(client, label: str, origin: str, *, ai_enabled: bool = False, ai_reply_mode: str = "draft_only"):
    auth, organization_id = await approved_workspace(client, label)
    created = await client.post(
        "/api/v1/integrations/widget",
        headers=bearer(auth["access_token"]),
        json={"allowed_origins": [origin], "collect_contact": True, "ai_enabled": ai_enabled, "ai_reply_mode": ai_reply_mode},
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
        json={"content": "Where is order 1001?", "visitor_email": "shopper@example.com", "contact_consent": True},
    )
    assert first.status_code == 201, first.text
    started = first.json()
    duplicate = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={**origin, "Idempotency-Key": "first-widget-message-key-01"},
        json={"content": "Where is order 1001?", "visitor_email": "shopper@example.com", "contact_consent": True},
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
        tickets = list(await db.scalars(select(Ticket).where(Ticket.organization_id == organization_id)))
        conversations = list(await db.scalars(select(Conversation).where(Conversation.organization_id == organization_id)))
        messages = list(await db.scalars(select(Message).where(Message.organization_id == organization_id)))
        executions = list(await db.scalars(select(AIExecution).where(AIExecution.organization_id == organization_id)))
        receipts = list(await db.scalars(select(WidgetSubmission).where(WidgetSubmission.organization_id == organization_id)))
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
    headers = {"Origin": "https://store-ai.example", "Idempotency-Key": "widget-ai-first-message-01"}
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

    @staticmethod
    def json():
        return {
            "choices": [{"message": {"content": "Our delivery fee is $5."}}],
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
        return WidgetMockProviderResponse()


@pytest.mark.anyio
async def test_widget_draft_only_saves_grounded_result_without_sending(client, monkeypatch):
    auth, organization_id, public_id = await setup_widget(
        client, "widget-draft-ai", "https://store-draft-ai.example", ai_enabled=True
    )
    user_id = UUID(auth["user"]["id"])
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        document = KnowledgeDocument(
            organization_id=organization_id,
            name="delivery-policy.txt",
            content_type="text/plain",
            size_bytes=40,
            status="ready",
            uploaded_by_user_id=user_id,
        )
        db.add(document)
        await db.flush()
        db.add(
            DocumentChunk(
                organization_id=organization_id,
                document_id=document.id,
                chunk_index=0,
                content="Our delivery charges are five dollars per order.",
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
    assert status_response.json()["draft"] == "Our delivery fee is $5."
    assert status_response.json()["citations"]
    history = await client.get(
        f"/api/v1/widget/conversations/{started.json()['conversation_id']}",
        headers={"Origin": origin, "Authorization": f"Bearer {started.json()['visitor_token']}"},
    )
    assert [message["sender_type"] for message in history.json()["messages"]] == ["customer"]


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
    assert [message["sender_type"] for message in history.json()["messages"]] == ["customer", "assistant"]
    assert "one-time code" in history.json()["messages"][-1]["content"]


@pytest.mark.anyio
async def test_widget_auto_reply_answers_standalone_greeting_without_knowledge_or_model(client, monkeypatch):
    auth, organization_id, public_id = await setup_widget(
        client,
        "widget-greeting-ai",
        "https://store-greeting-ai.example",
        ai_enabled=True,
        ai_reply_mode="auto_reply",
    )

    async def unexpected_model_call(*args, **kwargs):
        raise AssertionError("standalone greeting should not call the model")

    monkeypatch.setattr("app.services.ai_worker.create_grounded_draft", unexpected_model_call)
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
    assert [message["sender_type"] for message in history.json()["messages"]] == ["customer", "assistant"]
    assert history.json()["messages"][-1]["content"] == (
        "Hi there! I’m your store’s support assistant. I can help with order updates, product questions, "
        "and store policies. What can I help you with?"
    )


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
        headers={"Origin": "https://store-allowed.example", "Idempotency-Key": "honeypot-message-key-0001"},
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
async def test_widget_order_lookup_requires_email_code_and_returns_only_verified_tracking(client, monkeypatch):
    _auth, organization_id, public_id = await setup_widget(
        client,
        "widget-order-otp",
        "https://store-order-otp.example",
        ai_enabled=True,
        ai_reply_mode="auto_reply",
    )
    monkeypatch.setattr("app.api.routes.widgets.smtp_is_configured", lambda: True)
    monkeypatch.setattr("app.api.routes.widgets.encrypt_credential", lambda value: f"encrypted:{value}")
    monkeypatch.setattr("app.api.routes.widgets.decrypt_credential", lambda value: value.removeprefix("encrypted:"))
    monkeypatch.setattr(
        "app.services.shopify_security.decrypt_credential",
        lambda value: value.removeprefix("encrypted:"),
    )
    async def get_installation(db, org_id):
        return _installation()

    monkeypatch.setattr("app.api.routes.widgets.installation_for", get_installation)
    monkeypatch.setattr("app.api.routes.widgets.valid_access_token", lambda db, installation: _token())
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
            "fulfillments": [{"trackingInfo": [{"company": "Parcel Co", "number": "TRACK-1001", "url": "https://tracking.example/1001"}]}],
        }

    async def _send(email, code):
        return await send_code(email, code)

    monkeypatch.setattr("app.api.routes.widgets.send_order_verification_code", _send)
    monkeypatch.setattr("app.api.routes.widgets.lookup_authorized_order", find_order)
    origin = "https://store-order-otp.example"
    started = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={"Origin": origin, "Idempotency-Key": "widget-order-otp-message-1"},
        json={"content": "Where is my order?"},
    )
    assert started.status_code == 201, started.text
    visitor_headers = {"Origin": origin, "Authorization": f"Bearer {started.json()['visitor_token']}"}
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
    monkeypatch.setattr("app.api.routes.integrations.installation_for", get_installation)
    monkeypatch.setattr("app.api.routes.integrations.valid_access_token", lambda db, installation: _token())
    monkeypatch.setattr("app.services.shopify_orders.lookup_authorized_order", find_order)
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
    assert history_after_followup.json()["messages"][-1]["content"].startswith("I checked your verified order #1001.")
    conversation_after_verification = await client.get(
        f"/api/v1/widget/conversations/{started.json()['conversation_id']}",
        headers=visitor_headers,
    )
    assert conversation_after_verification.status_code == 200
    assert conversation_after_verification.json()["order_verified"] is True
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
    monkeypatch.setattr("app.api.routes.widgets.smtp_is_configured", lambda: True)
    monkeypatch.setattr("app.api.routes.widgets.encrypt_credential", lambda value: f"encrypted:{value}")

    async def get_installation(db, org_id):
        return _installation()

    async def find_order(**kwargs):
        return {"id": "gid://shopify/Order/2002", "name": "#2002"}

    async def fail_email(email, code):
        raise OSError("mock SMTP failure")

    monkeypatch.setattr("app.api.routes.widgets.installation_for", get_installation)
    monkeypatch.setattr("app.api.routes.widgets.valid_access_token", lambda db, installation: _token())
    monkeypatch.setattr("app.api.routes.widgets.lookup_authorized_order", find_order)
    monkeypatch.setattr("app.api.routes.widgets.send_order_verification_code", fail_email)

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
