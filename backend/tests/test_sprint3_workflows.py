import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.db.session import SessionLocal, set_tenant_context
from app.models import Message, PlatformOwner, Ticket

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Sprint 3 integration tests require the isolated test PostgreSQL service",
)


async def submit_registration(client, label: str):
    suffix = uuid4().hex[:10]
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"{label.title()} Workspace",
            "organization_slug": f"{label.lower()}-{suffix}",
            "full_name": "Workspace Owner",
            "email": f"owner-{suffix}@example.com",
            "password": "a-long-test-password",
        },
    )
    assert response.status_code == 202, response.text
    return {
        **response.json(),
        "email": f"owner-{suffix}@example.com",
        "password": "a-long-test-password",
    }


async def create_platform_owner(client):
    email = f"platform-{uuid4().hex[:10]}@example.com"
    password = "a-long-platform-test-password"
    async with SessionLocal() as session:
        session.add(PlatformOwner(email=email, password_hash=hash_password(password)))
        await session.commit()
    response = await client.post(
        "/api/v1/platform/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def register(client, label: str):
    registration = await submit_registration(client, label)
    platform = await create_platform_owner(client)
    tenants = await client.get(
        "/api/v1/platform/tenants?approval_status=pending",
        headers=auth(platform["access_token"]),
    )
    tenant_id = next(
        row["id"]
        for row in tenants.json()["items"]
        if row["slug"] == registration["organization_slug"]
    )
    approval = await client.post(
        f"/api/v1/platform/tenants/{tenant_id}/approve",
        headers=auth(platform["access_token"]),
    )
    assert approval.status_code == 200, approval.text
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": registration["organization_slug"],
            "email": registration["email"],
            "password": registration["password"],
        },
    )
    assert login.status_code == 200, login.text
    return login.json()


def auth(token: str):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_registration_refresh_rotation_and_logout(client):
    tokens = await register(client, "auth")
    assert tokens["user"]["role"] == "owner"
    assert tokens["expires_in"] == 900
    current = await client.get("/api/v1/auth/me", headers=auth(tokens["access_token"]))
    assert current.status_code == 200
    assert current.json()["organization"]["slug"]

    rotated = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != tokens["refresh_token"]
    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401
    revoked = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": rotated.json()["refresh_token"]}
    )
    assert revoked.status_code == 401

    login = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": current.json()["organization"]["slug"],
            "email": tokens["user"]["email"],
            "password": "a-long-test-password",
        },
    )
    assert login.status_code == 200
    logout = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": login.json()["refresh_token"]}
    )
    assert logout.status_code == 204
    expired = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login.json()["refresh_token"]}
    )
    assert expired.status_code == 401


@pytest.mark.anyio
async def test_tenant_registration_requires_platform_approval(client):
    registration = await submit_registration(client, "Approval")
    assert registration["status"] == "pending_approval"
    assert "access_token" not in registration
    assert "refresh_token" not in registration
    blocked_login = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": registration["organization_slug"],
            "email": registration["email"],
            "password": registration["password"],
        },
    )
    assert blocked_login.status_code == 403
    assert blocked_login.json()["detail"] == "Tenant registration is pending approval"
    assert blocked_login.json()["status"] == 403
    assert blocked_login.json()["code"] == "forbidden"

    platform = await create_platform_owner(client)
    unauthenticated = await client.get("/api/v1/platform/tenants")
    assert unauthenticated.status_code == 401
    pending = await client.get(
        "/api/v1/platform/tenants?approval_status=pending",
        headers=auth(platform["access_token"]),
    )
    tenant = next(
        row for row in pending.json()["items"] if row["slug"] == registration["organization_slug"]
    )
    assert tenant["requester_email"] == registration["email"]
    approved = await client.post(
        f"/api/v1/platform/tenants/{tenant['id']}/approve",
        headers=auth(platform["access_token"]),
    )
    assert approved.status_code == 200
    assert approved.json()["approval_status"] == "approved"
    assert approved.json()["reviewed_by_platform_owner_id"] == platform["platform_owner"]["id"]
    assert approved.json()["reviewed_at"]

    logged_in = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": registration["organization_slug"],
            "email": registration["email"],
            "password": registration["password"],
        },
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["role"] == "owner"
    tenant_token_denied = await client.get(
        "/api/v1/platform/tenants", headers=auth(logged_in.json()["access_token"])
    )
    assert tenant_token_denied.status_code == 401
    cross_refresh = await client.post(
        "/api/v1/platform/auth/refresh",
        json={"refresh_token": logged_in.json()["refresh_token"]},
    )
    assert cross_refresh.status_code == 401


@pytest.mark.anyio
async def test_rejected_tenant_is_preserved_and_can_be_reopened(client):
    registration = await submit_registration(client, "Rejected")
    platform = await create_platform_owner(client)
    headers = auth(platform["access_token"])
    pending = await client.get("/api/v1/platform/tenants", headers=headers)
    tenant = next(
        row for row in pending.json()["items"] if row["slug"] == registration["organization_slug"]
    )
    rejected = await client.post(f"/api/v1/platform/tenants/{tenant['id']}/reject", headers=headers)
    assert rejected.status_code == 200
    assert rejected.json()["approval_status"] == "rejected"

    login = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": registration["organization_slug"],
            "email": registration["email"],
            "password": registration["password"],
        },
    )
    assert login.status_code == 403
    assert login.json()["detail"] == "Tenant registration was rejected"
    assert login.json()["status"] == 403
    assert login.json()["code"] == "forbidden"

    duplicate_slug = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": registration["organization_name"],
            "organization_slug": registration["organization_slug"],
            "full_name": "Another Owner",
            "email": f"another-{uuid4().hex[:8]}@example.com",
            "password": "another-long-test-password",
        },
    )
    assert duplicate_slug.status_code == 409

    reopened = await client.post(f"/api/v1/platform/tenants/{tenant['id']}/reopen", headers=headers)
    assert reopened.status_code == 200
    assert reopened.json()["approval_status"] == "pending"
    approved = await client.post(
        f"/api/v1/platform/tenants/{tenant['id']}/approve", headers=headers
    )
    assert approved.status_code == 200
    after_approval = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": registration["organization_slug"],
            "email": registration["email"],
            "password": registration["password"],
        },
    )
    assert after_approval.status_code == 200


@pytest.mark.anyio
async def test_invitation_role_permissions_and_single_use(client):
    owner = await register(client, "team")
    invite = await client.post(
        "/api/v1/users/invitations",
        headers=auth(owner["access_token"]),
        json={"email": f"agent-{uuid4().hex[:8]}@example.com", "role": "agent"},
    )
    assert invite.status_code == 201, invite.text
    token = invite.json()["invite_token"]
    preview = await client.get(f"/api/v1/auth/invitations/{token}")
    assert preview.status_code == 200
    assert preview.json()["organization_name"] == "Team Workspace"
    accepted = await client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "invite_token": token,
            "full_name": "Support Agent",
            "password": "another-long-test-password",
        },
    )
    assert accepted.status_code == 201
    assert accepted.json()["user"]["role"] == "agent"
    used_again = await client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "invite_token": token,
            "full_name": "Support Agent",
            "password": "another-long-test-password",
        },
    )
    assert used_again.status_code == 400

    viewer_invite = await client.post(
        "/api/v1/users/invitations",
        headers=auth(owner["access_token"]),
        json={"email": f"viewer-{uuid4().hex[:8]}@example.com", "role": "viewer"},
    )
    viewer = await client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "invite_token": viewer_invite.json()["invite_token"],
            "full_name": "Read Only",
            "password": "viewer-long-password",
        },
    )
    assert viewer.status_code == 201
    denied = await client.post(
        "/api/v1/customers",
        headers=auth(viewer.json()["access_token"]),
        json={"name": "Blocked", "email": "blocked@example.com"},
    )
    assert denied.status_code == 403
    allowed = await client.get("/api/v1/customers", headers=auth(viewer.json()["access_token"]))
    assert allowed.status_code == 200

    last_owner = await client.patch(
        f"/api/v1/users/{owner['user']['id']}",
        headers=auth(owner["access_token"]),
        json={"is_active": False},
    )
    assert last_owner.status_code == 409


@pytest.mark.anyio
async def test_ticket_customer_message_search_stats_and_tenant_foreign_keys(client):
    owner = await register(client, "records")
    customer = await client.post(
        "/api/v1/customers",
        headers=auth(owner["access_token"]),
        json={"name": "Morgan Example", "email": "morgan@example.com"},
    )
    assert customer.status_code == 201
    ticket = await client.post(
        "/api/v1/tickets",
        headers=auth(owner["access_token"]),
        json={
            "customer_id": customer.json()["id"],
            "subject": "Order delivery question",
            "priority": "high",
        },
    )
    assert ticket.status_code == 201
    ticket_id = ticket.json()["id"]
    invitation = await client.post(
        "/api/v1/users/invitations",
        headers=auth(owner["access_token"]),
        json={"email": f"assignee-{uuid4().hex[:8]}@example.com", "role": "agent"},
    )
    agent = await client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "invite_token": invitation.json()["invite_token"],
            "full_name": "Assigned Agent",
            "password": "assigned-agent-password",
        },
    )
    assign = await client.patch(
        f"/api/v1/tickets/{ticket_id}",
        headers=auth(owner["access_token"]),
        json={"assignee_id": agent.json()["user"]["id"]},
    )
    assert assign.status_code == 200
    assert assign.json()["assignee_name"] == "Assigned Agent"

    page = await client.get(
        "/api/v1/tickets?search=delivery&priority=high", headers=auth(owner["access_token"])
    )
    assert page.status_code == 200
    assert page.json()["total"] >= 1
    assert page.json()["items"][0]["id"] == ticket_id
    customer_page = await client.get(
        f"/api/v1/customers/{customer.json()['id']}/tickets", headers=auth(owner["access_token"])
    )
    assert customer_page.json()["items"][0]["id"] == ticket_id

    conversation = await client.post(
        f"/api/v1/tickets/{ticket_id}/conversations",
        headers=auth(owner["access_token"]),
        json={"channel": "web"},
    )
    message = await client.post(
        f"/api/v1/conversations/{conversation.json()['id']}/messages",
        headers=auth(owner["access_token"]),
        json={"content": "I am checking on this for you."},
    )
    assert message.status_code == 201
    assert message.json()["sender_name"] == "Workspace Owner"
    history = await client.get(
        f"/api/v1/conversations/{conversation.json()['id']}/messages",
        headers=auth(owner["access_token"]),
    )
    assert history.json()[0]["sender_name"] == "Workspace Owner"
    activity = await client.get(
        f"/api/v1/tickets/{ticket_id}/activity", headers=auth(owner["access_token"])
    )
    assert {event["activity_type"] for event in activity.json()} >= {"created", "updated"}
    stats = await client.get("/api/v1/tickets/stats", headers=auth(owner["access_token"]))
    assert stats.status_code == 200
    assert stats.json()["total_tickets"] >= 1
    assert len(stats.json()["volume"]) == 30

    other = await register(client, "other")
    other_customer = await client.post(
        "/api/v1/customers",
        headers=auth(other["access_token"]),
        json={"name": "Other Tenant", "email": f"other-{uuid4().hex[:8]}@example.com"},
    )
    hidden = await client.get(f"/api/v1/tickets/{ticket_id}", headers=auth(other["access_token"]))
    assert hidden.status_code == 404

    async with SessionLocal() as session:
        owner_org = UUID(owner["user"]["organization_id"])
        await set_tenant_context(session, owner_org)
        session.add(
            Ticket(
                organization_id=owner_org,
                customer_id=UUID(other_customer.json()["id"]),
                subject="Tenant constraint check",
                status="open",
                priority="normal",
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.anyio
async def test_inbox_cursor_read_state_and_tenant_scope(client):
    owner = await register(client, "inbox")
    headers = auth(owner["access_token"])
    customer = await client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Inbox Customer", "email": "inbox-customer@example.com"},
    )
    assert customer.status_code == 201

    ticket_ids = []
    for index in range(3):
        ticket = await client.post(
            "/api/v1/tickets",
            headers=headers,
            json={
                "customer_id": customer.json()["id"],
                "subject": f"Inbox question {index}",
                "priority": "high" if index == 0 else "normal",
            },
        )
        assert ticket.status_code == 201
        ticket_ids.append(ticket.json()["id"])

    async with SessionLocal() as session:
        await set_tenant_context(session, UUID(owner["user"]["organization_id"]))
        tie_timestamp = datetime(2026, 10, 1, tzinfo=UTC)
        await session.execute(
            update(Ticket).where(Ticket.id.in_(ticket_ids[1:])).values(updated_at=tie_timestamp)
        )
        await session.commit()

    conversation = await client.post(
        f"/api/v1/tickets/{ticket_ids[0]}/conversations",
        headers=headers,
        json={"channel": "web"},
    )
    conversation_id = UUID(conversation.json()["id"])
    organization_id = UUID(owner["user"]["organization_id"])
    async with SessionLocal() as session:
        await set_tenant_context(session, organization_id)
        session.add_all(
            [
                Message(
                    organization_id=organization_id,
                    conversation_id=conversation_id,
                    sender_type="customer",
                    content="Where is my package?",
                ),
                Message(
                    organization_id=organization_id,
                    conversation_id=conversation_id,
                    sender_type="customer",
                    content="I have not received an update.",
                ),
            ]
        )
        await session.flush()
        await session.commit()

    first_page = await client.get("/api/v1/inbox?limit=1", headers=headers)
    assert first_page.status_code == 200, first_page.text
    assert first_page.json()["items"][0]["ticket_id"] in ticket_ids
    assert first_page.json()["items"][0]["conversation_id"] == str(conversation_id)
    assert first_page.json()["items"][0]["latest_message"]["preview"] == (
        "I have not received an update."
    )
    assert first_page.json()["items"][0]["unread_count"] == 2
    assert first_page.json()["next_cursor"]

    second_page = await client.get(
        f"/api/v1/inbox?limit=1&cursor={first_page.json()['next_cursor']}", headers=headers
    )
    assert second_page.status_code == 200, second_page.text
    assert second_page.json()["items"][0]["ticket_id"] != first_page.json()["items"][0]["ticket_id"]
    third_page = await client.get(
        f"/api/v1/inbox?limit=1&cursor={second_page.json()['next_cursor']}", headers=headers
    )
    assert [
        second_page.json()["items"][0]["ticket_id"],
        third_page.json()["items"][0]["ticket_id"],
    ] == sorted(ticket_ids[1:], reverse=True)

    high_priority = await client.get(
        "/api/v1/inbox?priority=high", headers=headers
    )
    assert [item["ticket_id"] for item in high_priority.json()["items"]] == [ticket_ids[0]]
    unassigned = await client.get("/api/v1/inbox?scope=unassigned", headers=headers)
    assert len(unassigned.json()["items"]) == 3

    marked = await client.post(
        f"/api/v1/conversations/{conversation_id}/read", headers=headers
    )
    assert marked.status_code == 200, marked.text
    cleared = await client.get("/api/v1/inbox?search=Inbox+question+0", headers=headers)
    assert cleared.json()["items"][0]["unread_count"] == 0

    invite = await client.post(
        "/api/v1/users/invitations",
        headers=headers,
        json={"email": "inbox-agent@example.com", "role": "agent"},
    )
    agent = await client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "invite_token": invite.json()["invite_token"],
            "full_name": "Inbox Agent",
            "password": "inbox-agent-password",
        },
    )
    other_member = await client.get(
        "/api/v1/inbox?search=Inbox+question+0", headers=auth(agent.json()["access_token"])
    )
    assert other_member.json()["items"][0]["unread_count"] == 2

    other_tenant = await register(client, "inboxother")
    hidden_read = await client.post(
        f"/api/v1/conversations/{conversation_id}/read",
        headers=auth(other_tenant["access_token"]),
    )
    assert hidden_read.status_code == 404
