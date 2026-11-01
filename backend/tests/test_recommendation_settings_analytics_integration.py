import os
from uuid import uuid4

import pytest

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import PlatformOwner

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Recommendation settings integration requires isolated PostgreSQL")


async def create_approved_workspace(client):
    suffix = uuid4().hex[:10]
    slug, email, password = f"recommend-{suffix}", f"owner-{suffix}@example.com", "recommend-owner-password"
    registration = await client.post("/api/v1/auth/register", json={
        "organization_name": "Recommendation Test",
        "organization_slug": slug,
        "full_name": "Recommendation Owner",
        "email": email,
        "password": password,
    })
    assert registration.status_code == 202, registration.text
    platform_email, platform_password = f"platform-{suffix}@example.com", "recommend-platform-password"
    async with SessionLocal() as db:
        db.add(PlatformOwner(email=platform_email, password_hash=hash_password(platform_password)))
        await db.commit()
    platform_login = await client.post("/api/v1/platform/auth/login", json={"email": platform_email, "password": platform_password})
    pending = await client.get("/api/v1/platform/tenants?approval_status=pending", headers={"Authorization": f"Bearer {platform_login.json()['access_token']}"})
    tenant = next(item for item in pending.json()["items"] if item["slug"] == slug)
    approved = await client.post(f"/api/v1/platform/tenants/{tenant['id']}/approve", headers={"Authorization": f"Bearer {platform_login.json()['access_token']}"})
    assert approved.status_code == 200
    login = await client.post("/api/v1/auth/login", json={"organization_slug": slug, "email": email, "password": password})
    assert login.status_code == 200, login.text
    return login.json(), slug


@pytest.mark.anyio
async def test_settings_and_recommendation_analytics_are_tenant_scoped_and_role_checked(client):
    owner, _slug = await create_approved_workspace(client)
    owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
    initial = await client.get("/api/v1/recommendation-settings", headers=owner_headers)
    assert initial.status_code == 200, initial.text
    assert initial.json()["max_products"] == 3
    update = await client.put("/api/v1/recommendation-settings", headers=owner_headers, json={
        "enabled": True,
        "mode": "explicit",
        "max_products": 2,
        "in_stock_only": True,
        "excluded_product_ids": [],
        "excluded_collection_ids": ["gid://shopify/Collection/123"],
        "comparison_enabled": False,
        "upselling_enabled": False,
        "cross_selling_enabled": False,
        "ranking_preferences": {"feature_match": 45},
        "human_handoff_preferences": {"enabled": True, "rejected_threshold": 4, "unsupported_threshold": 2},
    })
    assert update.status_code == 200, update.text
    assert update.json()["mode"] == "explicit"
    assert update.json()["max_products"] == 2

    invitation = await client.post("/api/v1/users/invitations", headers=owner_headers, json={"email": f"viewer-{uuid4().hex[:10]}@example.com", "role": "viewer"})
    assert invitation.status_code == 201, invitation.text
    viewer = await client.post("/api/v1/auth/invitations/accept", json={"invite_token": invitation.json()["invite_token"], "full_name": "Read Only", "password": "viewer-password-long-enough"})
    assert viewer.status_code == 201, viewer.text
    denied_payload = {key: value for key, value in update.json().items() if key not in {"id", "updated_at"}}
    denied = await client.put("/api/v1/recommendation-settings", headers={"Authorization": f"Bearer {viewer.json()['access_token']}"}, json=denied_payload)
    assert denied.status_code == 403

    analytics = await client.get("/api/v1/analytics/recommendations", headers=owner_headers)
    assert analytics.status_code == 200, analytics.text
    assert analytics.json()["conversion_tracking_available"] is False
    assert analytics.json()["attributed_purchases"] is None
