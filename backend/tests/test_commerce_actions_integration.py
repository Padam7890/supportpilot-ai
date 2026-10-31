import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal, set_tenant_context
from app.models import CommerceAction, PlatformOwner, User
from app.schemas.shopify import ShopifyOrderLookupOut
from app.services.commerce_action_worker import claim_commerce_action, process_commerce_action

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Commerce action integration tests require isolated PostgreSQL",
)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def register_owner(client, label: str):
    suffix = uuid4().hex[:10]
    email = f"owner-{suffix}@example.com"
    password = "commerce-owner-test-password"
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"{label.title()} Workspace",
            "organization_slug": f"{label}-{suffix}",
            "full_name": "Commerce Owner",
            "email": email,
            "password": password,
        },
    )
    assert registration.status_code == 202, registration.text

    platform_email = f"platform-{suffix}@example.com"
    platform_password = "commerce-platform-test-password"
    async with SessionLocal() as db:
        db.add(PlatformOwner(email=platform_email, password_hash=hash_password(platform_password)))
        await db.commit()
    platform_login = await client.post(
        "/api/v1/platform/auth/login",
        json={"email": platform_email, "password": platform_password},
    )
    assert platform_login.status_code == 200, platform_login.text
    pending = await client.get(
        "/api/v1/platform/tenants?approval_status=pending",
        headers=auth(platform_login.json()["access_token"]),
    )
    tenant_id = next(
        item["id"] for item in pending.json()["items"]
        if item["slug"] == registration.json()["organization_slug"]
    )
    approved = await client.post(
        f"/api/v1/platform/tenants/{tenant_id}/approve",
        headers=auth(platform_login.json()["access_token"]),
    )
    assert approved.status_code == 200, approved.text
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": registration.json()["organization_slug"],
            "email": email,
            "password": password,
        },
    )
    assert login.status_code == 200, login.text
    return login.json()


async def create_ticket(client, owner_tokens):
    headers = auth(owner_tokens["access_token"])
    customer = await client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Morgan Buyer", "email": "morgan@example.com"},
    )
    assert customer.status_code == 201, customer.text
    ticket = await client.post(
        "/api/v1/tickets",
        headers=headers,
        json={"customer_id": customer.json()["id"], "subject": "Damaged order item"},
    )
    assert ticket.status_code == 201, ticket.text
    return ticket.json()["id"]


def verified_shopify_order(customer_email: str) -> ShopifyOrderLookupOut:
    return ShopifyOrderLookupOut.model_validate(
        {
            "customer": {"display_name": "Morgan Buyer", "email": customer_email, "verified_by": "order_number_and_email"},
            "matched_order": {
                "id": "gid://shopify/Order/1001",
                "order_number": "#1001",
                "created_at": "2026-10-30T12:00:00Z",
                "financial_status": "PAID",
                "fulfillment_status": "FULFILLED",
                "total_amount": "42.50",
                "currency": "USD",
                "tracking": [],
            },
            "recent_orders": [],
            "has_next_page": False,
            "next_cursor": None,
        }
    )


async def add_teammate(organization_id: UUID, role: str) -> tuple[str, str]:
    email = f"{role}-{uuid4().hex[:10]}@example.com"
    password = "commerce-teammate-test-password"
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        db.add(
            User(
                organization_id=organization_id,
                email=email,
                full_name=f"Commerce {role.title()}",
                password_hash=hash_password(password),
                role=role,
                is_active=True,
            )
        )
        await db.commit()
    return email, password


async def login_teammate(client, slug: str, email: str, password: str):
    response = await client.post(
        "/api/v1/auth/login",
        json={"organization_slug": slug, "email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.anyio
async def test_agent_request_is_idempotent_owner_approval_executes_mock_and_audits(client, monkeypatch):
    owner = await register_owner(client, "commerce")
    profile = await client.get("/api/v1/auth/me", headers=auth(owner["access_token"]))
    organization_id = UUID(profile.json()["organization_id"])
    ticket_id = await create_ticket(client, owner)
    agent_email, agent_password = await add_teammate(organization_id, "agent")
    agent = await login_teammate(client, profile.json()["organization"]["slug"], agent_email, agent_password)
    verified_emails = []

    async def fake_verified_lookup(*, db, user, customer_email, order_number, limit, cursor):
        assert order_number == "1001"
        verified_emails.append(customer_email)
        return verified_shopify_order(customer_email)

    monkeypatch.setattr("app.api.routes.commerce_actions.verified_lookup", fake_verified_lookup)
    payload = {
        "ticket_id": ticket_id,
        "order_number": "1001",
        "action_type": "refund",
        "refund_amount": "12.50",
        "reason": "Customer received a damaged item",
    }
    headers = {**auth(agent["access_token"]), "Idempotency-Key": "commerce-refund-key-0001"}
    requested = await client.post("/api/v1/commerce/actions", headers=headers, json=payload)
    assert requested.status_code == 201, requested.text
    assert requested.json()["approval_status"] == "pending"
    assert requested.json()["execution_status"] == "not_started"
    assert requested.json()["requested_by_name"] == "Commerce Agent"
    assert "customer_email" not in requested.text

    repeated = await client.post("/api/v1/commerce/actions", headers=headers, json=payload)
    assert repeated.status_code == 201
    assert repeated.json()["id"] == requested.json()["id"]
    changed = await client.post(
        "/api/v1/commerce/actions",
        headers=headers,
        json={**payload, "reason": "Different reason"},
    )
    assert changed.status_code == 409
    assert verified_emails == ["morgan@example.com"]

    action_id = requested.json()["id"]
    approved = await client.post(
        f"/api/v1/commerce/actions/{action_id}/approve",
        headers=auth(owner["access_token"]),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approval_status"] == "approved"
    assert approved.json()["execution_status"] == "queued"
    assert approved.json()["reviewed_by_name"] == "Commerce Owner"
    duplicate_approval = await client.post(
        f"/api/v1/commerce/actions/{action_id}/approve",
        headers=auth(owner["access_token"]),
    )
    assert duplicate_approval.status_code == 409

    claimed = await claim_commerce_action(organization_id)
    assert str(claimed) == action_id
    await process_commerce_action(organization_id, claimed)
    finished = await client.get(
        f"/api/v1/commerce/actions/{action_id}", headers=auth(owner["access_token"])
    )
    assert finished.status_code == 200
    assert finished.json()["execution_status"] == "succeeded"
    assert finished.json()["execution_result"]["provider"] == "mock_commerce"
    audit = await client.get(
        f"/api/v1/commerce/actions/{action_id}/audit", headers=auth(owner["access_token"])
    )
    assert [item["event_type"] for item in audit.json()["items"]] == [
        "requested", "approved", "execution_started", "execution_succeeded"
    ]


@pytest.mark.anyio
async def test_viewer_cannot_request_or_approve_and_other_tenants_cannot_read_action(client, monkeypatch):
    owner = await register_owner(client, "commercepermissions")
    profile = await client.get("/api/v1/auth/me", headers=auth(owner["access_token"]))
    organization_id = UUID(profile.json()["organization_id"])
    ticket_id = await create_ticket(client, owner)
    viewer_email, viewer_password = await add_teammate(organization_id, "viewer")
    viewer = await login_teammate(client, profile.json()["organization"]["slug"], viewer_email, viewer_password)

    async def fake_verified_lookup(*, db, user, customer_email, order_number, limit, cursor):
        return verified_shopify_order(customer_email)

    monkeypatch.setattr("app.api.routes.commerce_actions.verified_lookup", fake_verified_lookup)
    payload = {
        "ticket_id": ticket_id,
        "order_number": "1001",
        "action_type": "cancel",
        "reason": "Customer changed their mind",
    }
    viewer_headers = {**auth(viewer["access_token"]), "Idempotency-Key": "commerce-cancel-key-0001"}
    denied_create = await client.post("/api/v1/commerce/actions", headers=viewer_headers, json=payload)
    assert denied_create.status_code == 403

    owner_headers = {**auth(owner["access_token"]), "Idempotency-Key": "commerce-cancel-key-0001"}
    action = await client.post("/api/v1/commerce/actions", headers=owner_headers, json=payload)
    assert action.status_code == 201, action.text
    denied_approval = await client.post(
        f"/api/v1/commerce/actions/{action.json()['id']}/approve",
        headers=auth(viewer["access_token"]),
    )
    assert denied_approval.status_code == 403
    viewer_list = await client.get("/api/v1/commerce/actions", headers=auth(viewer["access_token"]))
    assert viewer_list.status_code == 200
    assert viewer_list.json()["total"] == 1

    other_owner = await register_owner(client, "commerceother")
    hidden = await client.get(
        f"/api/v1/commerce/actions/{action.json()['id']}",
        headers=auth(other_owner["access_token"]),
    )
    assert hidden.status_code == 404


@pytest.mark.anyio
async def test_rejection_and_expiry_are_terminal_and_audited(client, monkeypatch):
    owner = await register_owner(client, "commerceexpiry")
    ticket_id = await create_ticket(client, owner)

    async def fake_verified_lookup(*, db, user, customer_email, order_number, limit, cursor):
        return verified_shopify_order(customer_email)

    monkeypatch.setattr("app.api.routes.commerce_actions.verified_lookup", fake_verified_lookup)

    async def request_cancel(key):
        return await client.post(
            "/api/v1/commerce/actions",
            headers={**auth(owner["access_token"]), "Idempotency-Key": key},
            json={"ticket_id": ticket_id, "order_number": "1001", "action_type": "cancel", "reason": "Please cancel this order"},
        )

    rejected = await request_cancel("commerce-reject-key-0001")
    assert rejected.status_code == 201, rejected.text
    rejected_result = await client.post(
        f"/api/v1/commerce/actions/{rejected.json()['id']}/reject",
        headers=auth(owner["access_token"]),
    )
    assert rejected_result.status_code == 200
    assert rejected_result.json()["approval_status"] == "rejected"
    assert rejected_result.json()["execution_status"] == "not_started"

    expired = await request_cancel("commerce-expire-key-0001")
    assert expired.status_code == 201, expired.text
    async with SessionLocal() as db:
        await set_tenant_context(db, UUID(owner["user"]["organization_id"]))
        row = await db.scalar(select(CommerceAction).where(CommerceAction.id == UUID(expired.json()["id"])))
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    approval = await client.post(
        f"/api/v1/commerce/actions/{expired.json()['id']}/approve",
        headers=auth(owner["access_token"]),
    )
    assert approval.status_code == 409
    expired_state = await client.get(
        f"/api/v1/commerce/actions/{expired.json()['id']}", headers=auth(owner["access_token"])
    )
    assert expired_state.json()["approval_status"] == "expired"
    assert expired_state.json()["execution_status"] == "not_started"


@pytest.mark.anyio
async def test_transient_mock_execution_failure_retries_within_bound_and_audits(client, monkeypatch):
    owner = await register_owner(client, "commerceretry")
    profile = await client.get("/api/v1/auth/me", headers=auth(owner["access_token"]))
    organization_id = UUID(profile.json()["organization_id"])
    ticket_id = await create_ticket(client, owner)

    async def fake_verified_lookup(*, db, user, customer_email, order_number, limit, cursor):
        return verified_shopify_order(customer_email)

    monkeypatch.setattr("app.api.routes.commerce_actions.verified_lookup", fake_verified_lookup)
    attempts = 0

    async def flaky_execute(self, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient simulation failure")
        return {
            "provider": "mock_commerce",
            "execution": "simulated",
            "operation_id": "stable-operation-id",
            "action_type": kwargs["action_type"],
            "order_number": kwargs["order_number"],
        }

    monkeypatch.setattr("app.services.commerce_action_worker.MockCommerceService.execute", flaky_execute)
    requested = await client.post(
        "/api/v1/commerce/actions",
        headers={**auth(owner["access_token"]), "Idempotency-Key": "commerce-retry-key-0001"},
        json={
            "ticket_id": ticket_id,
            "order_number": "1001",
            "action_type": "cancel",
            "reason": "Customer asked to cancel",
        },
    )
    assert requested.status_code == 201, requested.text
    action_id = requested.json()["id"]
    approved = await client.post(
        f"/api/v1/commerce/actions/{action_id}/approve",
        headers=auth(owner["access_token"]),
    )
    assert approved.status_code == 200

    first_claim = await claim_commerce_action(organization_id)
    await process_commerce_action(organization_id, first_claim)
    pending_retry = await client.get(f"/api/v1/commerce/actions/{action_id}", headers=auth(owner["access_token"]))
    assert pending_retry.json()["execution_status"] == "queued"
    assert pending_retry.json()["execution_attempt_count"] == 1

    second_claim = await claim_commerce_action(organization_id)
    await process_commerce_action(organization_id, second_claim)
    succeeded = await client.get(f"/api/v1/commerce/actions/{action_id}", headers=auth(owner["access_token"]))
    assert succeeded.json()["execution_status"] == "succeeded"
    assert succeeded.json()["execution_attempt_count"] == 2
    audit = await client.get(f"/api/v1/commerce/actions/{action_id}/audit", headers=auth(owner["access_token"]))
    assert [item["event_type"] for item in audit.json()["items"]] == [
        "requested", "approved", "execution_started", "execution_retry_scheduled", "execution_started", "execution_succeeded"
    ]

