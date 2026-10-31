import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal, set_tenant_context
from app.models import Ticket

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Sprint 3 integration tests require the isolated test PostgreSQL service",
)


async def register(client, label: str):
    suffix = uuid4().hex[:10]
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"{label} Workspace",
            "organization_slug": f"{label.lower()}-{suffix}",
            "full_name": "Workspace Owner",
            "email": f"owner-{suffix}@example.test",
            "password": "a-long-test-password",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


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
async def test_invitation_role_permissions_and_single_use(client):
    owner = await register(client, "team")
    invite = await client.post(
        "/api/v1/users/invitations",
        headers=auth(owner["access_token"]),
        json={"email": f"agent-{uuid4().hex[:8]}@example.test", "role": "agent"},
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
        json={"email": f"viewer-{uuid4().hex[:8]}@example.test", "role": "viewer"},
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
        json={"name": "Blocked", "email": "blocked@example.test"},
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
        json={"name": "Morgan Example", "email": "morgan@example.test"},
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
        json={"email": f"assignee-{uuid4().hex[:8]}@example.test", "role": "agent"},
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
        json={"name": "Other Tenant", "email": f"other-{uuid4().hex[:8]}@example.test"},
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
