import asyncio
import os
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.api.routes import ai as ai_routes
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal, set_tenant_context
from app.integrations.providers.shopify import security as shopify_security
from app.models import (
    AIAgent,
    AIExecution,
    Conversation,
    Customer,
    DocumentChunk,
    KnowledgeBase,
    KnowledgeDocument,
    Message,
    PlatformOwner,
    Ticket,
    User,
)
from app.schemas.shopify import ShopifyOrderLookupOut, ShopifyOrderOut
from app.services.ai_worker import claim_ai_execution, process_ai_execution
from app.worker import claim_one, process_job
from tests.auth_helpers import verify_registration, workspace_login

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="AI execution integration tests require isolated PostgreSQL",
)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def platform_owner(client):
    email = f"ai-platform-{uuid4().hex[:8]}@example.com"
    password = "ai-platform-test-password"
    async with SessionLocal() as db:
        db.add(PlatformOwner(email=email, password_hash=hash_password(password)))
        await db.commit()
    response = await client.post(
        "/api/v1/platform/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def approved_workspace(client, platform, label: str):
    suffix = uuid4().hex[:10]
    slug = f"{label}-{suffix}"
    email = f"{label}-{suffix}@example.com"
    password = "ai-workspace-test-password"
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"{label.title()} Workspace",
            "organization_slug": slug,
            "full_name": "AI Test Owner",
            "email": email,
            "password": password,
        },
    )
    assert registration.status_code == 202, registration.text
    await verify_registration(client, registration, email)
    pending = await client.get(
        "/api/v1/platform/tenants?approval_status=pending",
        headers=bearer(platform["access_token"]),
    )
    tenant = next(item for item in pending.json()["items"] if item["slug"] == slug)
    approved = await client.post(
        f"/api/v1/platform/tenants/{tenant['id']}/approve",
        headers=bearer(platform["access_token"]),
    )
    assert approved.status_code == 200
    return await workspace_login(client, email, password, slug)


class MockProviderResponse:
    status_code = 200
    is_error = False

    @staticmethod
    def json():
        return {
            "choices": [
                {"message": {"content": "Unused products may be returned within thirty days."}}
            ],
            "usage": {"prompt_tokens": 21, "completion_tokens": 11, "total_tokens": 32},
        }


class MockProviderClient:
    last_request = None

    def __init__(self, *args, **kwargs):
        self.request_json = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, *, headers, json):
        self.request_json = json
        type(self).last_request = json
        assert url.endswith("/chat/completions")
        assert "authorization" not in headers
        return MockProviderResponse()


@pytest.mark.anyio
async def test_ai_reply_draft_is_grounded_safe_and_never_sent(client, monkeypatch):
    platform = await platform_owner(client)
    owner = await approved_workspace(client, platform, "ai-draft")
    organization_id = UUID(owner["user"]["organization_id"])
    user_id = UUID(owner["user"]["id"])

    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        customer = Customer(
            organization_id=organization_id,
            name="Riley Customer",
            email=f"riley-{uuid4().hex[:8]}@example.com",
        )
        db.add(customer)
        await db.flush()
        ticket = Ticket(
            organization_id=organization_id,
            customer_id=customer.id,
            subject="Return request",
            status="open",
            priority="normal",
        )
        db.add(ticket)
        await db.flush()
        agent = await db.scalar(select(AIAgent).where(AIAgent.organization_id == organization_id, AIAgent.is_default.is_(True)))
        base = await db.scalar(select(KnowledgeBase).where(KnowledgeBase.organization_id == organization_id, KnowledgeBase.is_default.is_(True)))
        conversation = Conversation(organization_id=organization_id, ticket_id=ticket.id, ai_agent_id=agent.id)
        db.add(conversation)
        await db.flush()
        db.add_all(
            [
                Message(
                    organization_id=organization_id,
                    conversation_id=conversation.id,
                    sender_type="internal_note",
                    sender_user_id=user_id,
                    content="PRIVATE TEAM NOTE: escalate only if outside 30 days.",
                ),
                Message(
                    organization_id=organization_id,
                    conversation_id=conversation.id,
                    sender_type="customer",
                    content="Can I return an unused item?",
                ),
            ]
        )
        document = KnowledgeDocument(
            organization_id=organization_id,
            name="returns-policy.txt",
            content_type="text/plain",
            size_bytes=64,
            status="ready",
            uploaded_by_user_id=user_id,
            knowledge_base_id=base.id,
        )
        db.add(document)
        await db.flush()
        db.add(
            DocumentChunk(
                organization_id=organization_id,
                document_id=document.id,
                chunk_index=0,
                content="Unused products may be returned within thirty days with proof of purchase.",
            )
        )
        await db.commit()
        conversation_id = conversation.id

    monkeypatch.setattr(settings, "ai_provider_base_url", "http://127.0.0.1:8012/v1")
    monkeypatch.setattr(settings, "ai_model", "test-support-model")
    monkeypatch.setattr(settings, "ai_provider_api_key", None)
    monkeypatch.setattr(httpx, "AsyncClient", MockProviderClient)
    verified_order_email = customer.email

    async def mock_verified_lookup(**kwargs):
        assert kwargs["customer_email"] == verified_order_email
        assert kwargs["order_number"] == "#42"
        return ShopifyOrderLookupOut(
            customer={
                "display_name": "Riley Customer",
                "email": verified_order_email,
                "verified_by": "order_number_and_email",
            },
            matched_order=ShopifyOrderOut(
                id="gid://shopify/Order/42",
                order_number="#42",
                created_at="2026-01-01T00:00:00Z",
                financial_status="PAID",
                fulfillment_status="FULFILLED",
                total_amount="19.95",
                currency="USD",
                tracking=[],
            ),
            recent_orders=[],
            has_next_page=False,
            next_cursor=None,
        )

    monkeypatch.setattr(ai_routes, "verified_lookup", mock_verified_lookup)
    monkeypatch.setattr(ai_routes, "encrypt_credential", lambda value: f"sealed:{value}")
    monkeypatch.setattr(
        shopify_security,
        "decrypt_credential",
        lambda value: value.removeprefix("sealed:"),
    )
    queued = await client.post(
        "/api/v1/ai/reply-drafts",
        headers=bearer(owner["access_token"]),
        json={
            "conversation_id": str(conversation_id),
            "instructions": "Be concise",
            "shopify_order_number": "#42",
        },
    )
    assert queued.status_code == 202, queued.text
    response_body = queued.json()
    assert response_body["status"] == "queued"
    assert "question" not in response_body
    assert "instructions" not in response_body
    assert "integration_context_encrypted" not in response_body
    assert "shopify_order_number" not in response_body

    execution_id = UUID(response_body["id"])
    claimed = await claim_ai_execution(organization_id)
    assert claimed == execution_id
    await process_ai_execution(organization_id, execution_id)

    result = await client.get(
        f"/api/v1/ai/executions/{execution_id}", headers=bearer(owner["access_token"])
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "succeeded"
    assert result.json()["draft"] == "Unused products may be returned within thirty days."
    assert result.json()["citations"][0]["document_name"] == "returns-policy.txt"
    assert result.json()["usage"]["total_tokens"] == 32
    assert "reasoning" not in result.text.lower()
    assert "PRIVATE TEAM NOTE" not in str(MockProviderClient.last_request)
    assert '"order_number": "#42"' in str(MockProviderClient.last_request)
    assert verified_order_email not in str(MockProviderClient.last_request)

    evaluation_payload = {
        "execution_id": str(execution_id),
        "rating": "helpful",
        "category": "grounding",
    }
    evaluation = await client.post(
        "/api/v1/analytics/evaluations",
        headers=bearer(owner["access_token"]),
        json=evaluation_payload,
    )
    assert evaluation.status_code == 200, evaluation.text
    changed_evaluation = await client.post(
        "/api/v1/analytics/evaluations",
        headers=bearer(owner["access_token"]),
        json={**evaluation_payload, "rating": "not_helpful", "category": "accuracy"},
    )
    assert changed_evaluation.status_code == 200
    summary = await client.get(
        "/api/v1/analytics/evaluations", headers=bearer(owner["access_token"])
    )
    assert summary.status_code == 200, summary.text
    assert summary.json()["rated"] == 1
    assert summary.json()["helpful"] == 0
    assert summary.json()["not_helpful"] == 1
    usage = await client.get(
        "/api/v1/analytics/ai-usage", headers=bearer(owner["access_token"])
    )
    assert usage.status_code == 200, usage.text
    assert usage.json()["executions"] == 1
    assert usage.json()["total_tokens"] == 32

    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        message_count = await db.scalar(
            select(func.count(Message.id)).where(
                Message.organization_id == organization_id,
                Message.conversation_id == conversation_id,
            )
        )
        assert message_count == 2
        execution = await db.scalar(
            select(AIExecution).where(
                AIExecution.id == execution_id,
                AIExecution.organization_id == organization_id,
            )
        )
        assert execution is not None
        assert execution.integration_context_encrypted is None
        execution.question = "sensitive private prompt that should never be in the response"
        execution.instructions = "sensitive private instructions"
        await db.commit()

    other_owner = await approved_workspace(client, platform, "ai-other")
    other_summary = await client.get(
        "/api/v1/analytics/evaluations", headers=bearer(other_owner["access_token"])
    )
    assert other_summary.status_code == 200
    assert other_summary.json()["rated"] == 0
    cross_tenant_rating = await client.post(
        "/api/v1/analytics/evaluations",
        headers=bearer(other_owner["access_token"]),
        json=evaluation_payload,
    )
    assert cross_tenant_rating.status_code == 404
    isolated = await client.get(
        f"/api/v1/ai/executions/{execution_id}", headers=bearer(other_owner["access_token"])
    )
    assert isolated.status_code == 404

    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        user = await db.get(User, user_id)
        assert user is not None
        user.role = "viewer"
        await db.commit()
    forbidden = await client.post(
        "/api/v1/ai/playground",
        headers=bearer(owner["access_token"]),
        json={"question": "What is the return policy?"},
    )
    assert forbidden.status_code == 403


@pytest.mark.anyio
async def test_uploaded_document_flows_through_assigned_bot_to_scoped_citation(client, monkeypatch):
    platform = await platform_owner(client)
    owner = await approved_workspace(client, platform, "ai-kb-flow")
    headers = bearer(owner["access_token"])
    organization_id = UUID(owner["user"]["organization_id"])

    returns_base = await client.post(
        "/api/v1/knowledge/bases", headers=headers, json={"name": "Returns"}
    )
    shipping_base = await client.post(
        "/api/v1/knowledge/bases", headers=headers, json={"name": "Shipping"}
    )
    assert returns_base.status_code == shipping_base.status_code == 201
    returns_bot = await client.post(
        "/api/v1/ai/agents",
        headers=headers,
        json={
            "name": "Returns assistant",
            "system_instructions": "Answer using the assigned return policy.",
            "knowledge_base_ids": [returns_base.json()["id"]],
        },
    )
    assert returns_bot.status_code == 201, returns_bot.text

    uploaded_documents = []
    for name, knowledge_base, contents in (
        (
            "returns-policy.txt",
            returns_base.json(),
            b"Unused items may be returned within thirty days with proof of purchase.",
        ),
        (
            "shipping-policy.txt",
            shipping_base.json(),
            b"Standard shipping takes five business days.",
        ),
    ):
        uploaded = await client.post(
            "/api/v1/knowledge/documents",
            params={"name": name, "knowledge_base_id": knowledge_base["id"]},
            headers={**headers, "content-type": "text/plain"},
            content=contents,
        )
        assert uploaded.status_code == 202, uploaded.text
        uploaded_documents.append(uploaded.json())
        claim = await claim_one(organization_id)
        assert claim is not None and claim[1] == UUID(uploaded.json()["id"])
        await process_job(organization_id, *claim)

    for uploaded in uploaded_documents:
        ready = await client.get(
            f"/api/v1/knowledge/documents/{uploaded['id']}", headers=headers
        )
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"

    monkeypatch.setattr(settings, "ai_provider_base_url", "http://127.0.0.1:8012/v1")
    monkeypatch.setattr(settings, "ai_model", "test-support-model")
    monkeypatch.setattr(settings, "ai_provider_api_key", None)
    monkeypatch.setattr(httpx, "AsyncClient", MockProviderClient)
    queued = await client.post(
        "/api/v1/ai/playground",
        headers=headers,
        json={
            "question": "Can I return an unused item?",
            "ai_agent_id": returns_bot.json()["id"],
        },
    )
    assert queued.status_code == 202, queued.text
    execution_id = UUID(queued.json()["id"])
    assert await claim_ai_execution(organization_id) == execution_id
    await process_ai_execution(organization_id, execution_id)

    result = await client.get(f"/api/v1/ai/executions/{execution_id}", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "succeeded"
    assert [citation["document_name"] for citation in result.json()["citations"]] == [
        "returns-policy.txt"
    ]
    assert "shipping-policy.txt" not in str(result.json()["citations"])
    assert result.json()["draft"] == "Unused products may be returned within thirty days."


@pytest.mark.anyio
async def test_playground_without_assigned_knowledge_completes_without_calling_model(client, monkeypatch):
    platform = await platform_owner(client)
    owner = await approved_workspace(client, platform, "ai-no-assigned-knowledge")
    headers = bearer(owner["access_token"])
    organization_id = UUID(owner["user"]["organization_id"])
    monkeypatch.setattr(settings, "ai_provider_base_url", "http://127.0.0.1:8012/v1")
    monkeypatch.setattr(settings, "ai_model", "test-support-model")
    monkeypatch.setattr(httpx, "AsyncClient", MockProviderClient)
    MockProviderClient.last_request = None

    bot = await client.post(
        "/api/v1/ai/agents",
        headers=headers,
        json={"name": "Unassigned sources bot", "knowledge_base_ids": []},
    )
    assert bot.status_code == 201, bot.text
    queued = await client.post(
        "/api/v1/ai/playground",
        headers=headers,
        json={
            "question": "What is this store's return policy?",
            "ai_agent_id": bot.json()["id"],
        },
    )
    assert queued.status_code == 202, queued.text
    execution_id = UUID(queued.json()["id"])
    assert await claim_ai_execution(organization_id) == execution_id
    await process_ai_execution(organization_id, execution_id)

    result = await client.get(f"/api/v1/ai/executions/{execution_id}", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "succeeded"
    assert result.json()["citations"] == []
    assert "assigned knowledge sources" in result.json()["draft"]
    assert result.json()["usage"] == {}
    assert MockProviderClient.last_request is None


@pytest.mark.anyio
async def test_ai_active_execution_limit_is_enforced_under_concurrent_requests(client, monkeypatch):
    platform = await platform_owner(client)
    owner = await approved_workspace(client, platform, "ai-cap")
    monkeypatch.setattr(settings, "ai_provider_base_url", "http://127.0.0.1:8012/v1")
    monkeypatch.setattr(settings, "ai_model", "test-support-model")

    responses = await asyncio.gather(
        *[
            client.post(
                "/api/v1/ai/playground",
                headers=bearer(owner["access_token"]),
                json={"question": f"Concurrent test question {index}?"},
            )
            for index in range(12)
        ]
    )

    assert sum(response.status_code == 202 for response in responses) == 10
    assert sum(response.status_code == 429 for response in responses) == 2
    assert all(response.status_code in {202, 429} for response in responses)
    organization_id = UUID(owner["user"]["organization_id"])
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        active_count = await db.scalar(
            select(func.count(AIExecution.id)).where(
                AIExecution.organization_id == organization_id,
                AIExecution.status.in_(("queued", "running")),
            )
        )
        assert active_count == 10
        await db.rollback()
