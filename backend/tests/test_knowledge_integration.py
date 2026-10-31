import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update

from app.core.security import hash_password
from app.db.session import SessionLocal, set_tenant_context
from app.models import (
    DocumentChunk,
    DocumentIngestionJob,
    KnowledgeDocumentSource,
    PlatformOwner,
)
from app.worker import claim_one, process_job

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Knowledge integration tests require isolated PostgreSQL",
)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def approved_workspace(client, prefix: str) -> dict:
    suffix = uuid4().hex[:10]
    slug = f"{prefix}-{suffix}"
    email = f"{prefix}-{suffix}@example.com"
    password = "knowledge-test-owner-password"
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"{prefix.title()} Workspace",
            "organization_slug": slug,
            "full_name": "Knowledge Owner",
            "email": email,
            "password": password,
        },
    )
    assert registration.status_code == 202, registration.text
    platform_email = f"platform-{suffix}@example.com"
    platform_password = "platform-owner-test-password"
    async with SessionLocal() as session:
        session.add(
            PlatformOwner(email=platform_email, password_hash=hash_password(platform_password))
        )
        await session.commit()
    platform = await client.post(
        "/api/v1/platform/auth/login",
        json={"email": platform_email, "password": platform_password},
    )
    pending = await client.get(
        "/api/v1/platform/tenants?approval_status=pending",
        headers=bearer(platform.json()["access_token"]),
    )
    tenant = next(item for item in pending.json()["items"] if item["slug"] == slug)
    approved = await client.post(
        f"/api/v1/platform/tenants/{tenant['id']}/approve",
        headers=bearer(platform.json()["access_token"]),
    )
    assert approved.status_code == 200, approved.text
    login = await client.post(
        "/api/v1/auth/login",
        json={"organization_slug": slug, "email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return login.json()


async def upload_text(client, owner: dict, name: str, content: bytes):
    return await client.post(
        "/api/v1/knowledge/documents",
        params={"name": name},
        content=content,
        headers={**bearer(owner["access_token"]), "content-type": "text/plain"},
    )


@pytest.mark.anyio
async def test_document_processing_search_reprocess_and_tenant_isolation(client):
    owner = await approved_workspace(client, "knowledge")
    uploaded = await upload_text(
        client,
        owner,
        "returns-policy.txt",
        b"Customers may return unused items within thirty days with proof of purchase.",
    )
    assert uploaded.status_code == 202, uploaded.text
    document = uploaded.json()
    assert document["status"] == "queued"
    assert len(document["jobs"]) == 1
    organization_id = UUID(owner["user"]["organization_id"])
    claimed = await claim_one(organization_id)
    assert claimed is not None
    await process_job(organization_id, *claimed)

    ready = await client.get(
        f"/api/v1/knowledge/documents/{document['id']}", headers=bearer(owner["access_token"])
    )
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["jobs"][0]["status"] == "succeeded"

    results = await client.get(
        "/api/v1/knowledge/documents/search?q=thirty+days",
        headers=bearer(owner["access_token"]),
    )
    assert results.status_code == 200
    assert results.json()["items"][0]["document_id"] == document["id"]
    assert results.json()["items"][0]["chunk_index"] == 0

    reprocessed = await client.post(
        f"/api/v1/knowledge/documents/{document['id']}/reprocess",
        headers=bearer(owner["access_token"]),
    )
    assert reprocessed.status_code == 202
    assert len(reprocessed.json()["jobs"]) == 2

    # Removing a document must clean searchable/source data without cascading
    # away its durable document and ingestion audit history.
    removed = await client.delete(
        f"/api/v1/knowledge/documents/{document['id']}",
        headers=bearer(owner["access_token"]),
    )
    assert removed.status_code == 204
    assert await claim_one(organization_id) is None
    removed_detail = await client.get(
        f"/api/v1/knowledge/documents/{document['id']}",
        headers=bearer(owner["access_token"]),
    )
    assert removed_detail.status_code == 200
    assert removed_detail.json()["deleted_at"] is not None
    assert [job["status"] for job in removed_detail.json()["jobs"]] == [
        "cancelled",
        "succeeded",
    ]
    removed_list = await client.get(
        "/api/v1/knowledge/documents", headers=bearer(owner["access_token"])
    )
    assert removed_list.json()["total"] == 0
    removed_search = await client.get(
        "/api/v1/knowledge/documents/search?q=thirty+days",
        headers=bearer(owner["access_token"]),
    )
    assert removed_search.status_code == 200
    assert removed_search.json()["total"] == 0
    refused_reprocess = await client.post(
        f"/api/v1/knowledge/documents/{document['id']}/reprocess",
        headers=bearer(owner["access_token"]),
    )
    assert refused_reprocess.status_code == 404
    async with SessionLocal() as session:
        await set_tenant_context(session, organization_id)
        assert await session.get(
            KnowledgeDocumentSource, (organization_id, UUID(document["id"]))
        ) is None
        chunk_count = await session.scalar(
            select(DocumentChunk.id).where(
                DocumentChunk.organization_id == organization_id,
                DocumentChunk.document_id == UUID(document["id"]),
            )
        )
        assert chunk_count is None
        retained_jobs = list(
            await session.scalars(
                select(DocumentIngestionJob).where(
                    DocumentIngestionJob.organization_id == organization_id,
                    DocumentIngestionJob.document_id == UUID(document["id"]),
                )
            )
        )
        assert len(retained_jobs) == 2
        await session.rollback()

    other_owner = await approved_workspace(client, "knowledge-other")
    hidden = await client.get(
        f"/api/v1/knowledge/documents/{document['id']}",
        headers=bearer(other_owner["access_token"]),
    )
    assert hidden.status_code == 404
    other_list = await client.get(
        "/api/v1/knowledge/documents", headers=bearer(other_owner["access_token"])
    )
    assert other_list.json()["total"] == 0


@pytest.mark.anyio
async def test_ingestion_retry_limit_and_reprocess_history(client):
    owner = await approved_workspace(client, "knowledge-retry")
    uploaded = await upload_text(client, owner, "invalid-encoding.txt", b"\xff")
    assert uploaded.status_code == 202
    document_id = UUID(uploaded.json()["id"])
    organization_id = UUID(owner["user"]["organization_id"])
    duplicate_reprocess = await client.post(
        f"/api/v1/knowledge/documents/{document_id}/reprocess",
        headers=bearer(owner["access_token"]),
    )
    assert duplicate_reprocess.status_code == 409
    assert "already queued or running" in duplicate_reprocess.json()["detail"]

    for attempt in range(1, 4):
        claimed = await claim_one(organization_id)
        assert claimed is not None
        await process_job(organization_id, *claimed)
        async with SessionLocal() as session:
            await set_tenant_context(session, organization_id)
            job = await session.scalar(
                select(DocumentIngestionJob).where(
                    DocumentIngestionJob.document_id == document_id
                )
            )
            assert job is not None
            assert job.attempt_count == attempt
            if attempt < 3:
                await session.execute(
                    update(DocumentIngestionJob)
                    .where(DocumentIngestionJob.id == job.id)
                    .values(next_attempt_at=datetime.now(UTC) - timedelta(seconds=1))
                )
            else:
                assert job.status == "failed"
                assert job.last_error
            await session.commit()

    reprocessed = await client.post(
        f"/api/v1/knowledge/documents/{document_id}/reprocess",
        headers=bearer(owner["access_token"]),
    )
    assert reprocessed.status_code == 202
    assert len(reprocessed.json()["jobs"]) == 2
    assert reprocessed.json()["jobs"][0]["attempt_count"] == 0
