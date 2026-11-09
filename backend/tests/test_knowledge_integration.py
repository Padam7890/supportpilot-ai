import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.exc import IntegrityError

from app.core.security import create_access_token, hash_password
from app.db.session import SessionLocal, engine, set_tenant_context
from app.features.ai.application.context import load_execution_context
from app.models import (
    AIAgentKnowledgeBase,
    AIExecution,
    DocumentChunk,
    DocumentEmbedding,
    DocumentIngestionJob,
    KnowledgeDocument,
    KnowledgeDocumentSource,
    PlatformOwner,
    User,
)
from app.worker import claim_one, process_job
from tests.auth_helpers import verify_registration, workspace_login
from tests.rag_fixtures import hash_chunk_text, hash_document_text

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
    await verify_registration(client, registration, email)
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
    return await workspace_login(client, email, password, slug)


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
        assert (
            await session.get(KnowledgeDocumentSource, (organization_id, UUID(document["id"])))
            is None
        )
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
                select(DocumentIngestionJob).where(DocumentIngestionJob.document_id == document_id)
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


@pytest.mark.anyio
async def test_ingestion_claims_are_exclusive_and_stale_leases_are_recovered(client):
    owner = await approved_workspace(client, "knowledge-lease")
    uploaded = await upload_text(client, owner, "lease.txt", b"A durable lease test document.")
    assert uploaded.status_code == 202, uploaded.text
    document_id = UUID(uploaded.json()["id"])
    organization_id = UUID(owner["user"]["organization_id"])

    first, second = await asyncio.gather(
        claim_one(organization_id),
        claim_one(organization_id),
    )
    assert sum(claim is not None for claim in (first, second)) == 1
    claimed = first or second
    assert claimed is not None and claimed[1] == document_id

    async with SessionLocal() as session:
        await set_tenant_context(session, organization_id)
        job = await session.scalar(
            select(DocumentIngestionJob).where(
                DocumentIngestionJob.organization_id == organization_id,
                DocumentIngestionJob.id == claimed[0],
            )
        )
        assert job is not None
        job.status = "running"
        job.updated_at = datetime.now(UTC) - timedelta(minutes=6)
        await session.commit()

    reclaimed = await claim_one(organization_id)
    assert reclaimed == claimed
    async with SessionLocal() as session:
        await set_tenant_context(session, organization_id)
        job = await session.scalar(
            select(DocumentIngestionJob).where(
                DocumentIngestionJob.organization_id == organization_id,
                DocumentIngestionJob.id == claimed[0],
            )
        )
        assert job is not None and job.attempt_count == 2
        await session.rollback()


@pytest.mark.anyio
async def test_ingestion_claim_is_tenant_scoped(client):
    owner_a = await approved_workspace(client, "knowledge-tenant-a")
    owner_b = await approved_workspace(client, "knowledge-tenant-b")
    uploaded_a = await upload_text(client, owner_a, "a.txt", b"Tenant A document")
    uploaded_b = await upload_text(client, owner_b, "b.txt", b"Tenant B document")
    assert uploaded_a.status_code == uploaded_b.status_code == 202

    organization_a = UUID(owner_a["user"]["organization_id"])
    claimed = await claim_one(organization_a)
    assert claimed is not None
    assert claimed[1] == UUID(uploaded_a.json()["id"])
    assert claimed[1] != UUID(uploaded_b.json()["id"])


@pytest.mark.anyio
async def test_default_ai_configuration_and_cross_tenant_assignments(client):
    owner_a = await approved_workspace(client, "ai-agent-a")
    owner_b = await approved_workspace(client, "ai-agent-b")
    headers_a = bearer(owner_a["access_token"])
    headers_b = bearer(owner_b["access_token"])
    bases_a = (await client.get("/api/v1/knowledge/bases", headers=headers_a)).json()
    agents_a = (await client.get("/api/v1/ai/agents", headers=headers_a)).json()
    assert len(bases_a["items"]) == 1 and bases_a["items"][0]["is_default"] is True
    assert len(agents_a["items"]) == 1 and agents_a["items"][0]["is_default"] is True
    assert agents_a["items"][0]["knowledge_base_ids"] == [bases_a["items"][0]["id"]]

    base_a = (
        await client.post(
            "/api/v1/knowledge/bases", headers=headers_a, json={"name": "Private policies"}
        )
    ).json()
    shared_base = (
        await client.post(
            "/api/v1/knowledge/bases", headers=headers_a, json={"name": "Shared product facts"}
        )
    ).json()
    base_b = (
        await client.post(
            "/api/v1/knowledge/bases", headers=headers_b, json={"name": "Other tenant"}
        )
    ).json()
    rejected = await client.post(
        "/api/v1/ai/agents",
        headers=headers_a,
        json={"name": "Cross tenant attempt", "knowledge_base_ids": [base_b["id"]]},
    )
    assert rejected.status_code == 422
    created = await client.post(
        "/api/v1/ai/agents",
        headers=headers_a,
        json={
            "name": "Returns assistant",
            "system_instructions": "Be concise.",
            "knowledge_base_ids": [base_a["id"], shared_base["id"]],
        },
    )
    assert created.status_code == 201, created.text
    assert set(created.json()["knowledge_base_ids"]) == {base_a["id"], shared_base["id"]}
    second = await client.post(
        "/api/v1/ai/agents",
        headers=headers_a,
        json={
            "name": "Product assistant",
            "knowledge_base_ids": [shared_base["id"]],
        },
    )
    assert second.status_code == 201, second.text
    assert second.json()["knowledge_base_ids"] == [shared_base["id"]]

    assignment_queries = 0

    def count_assignment_query(_connection, _cursor, statement, _parameters, _context, _many):
        nonlocal assignment_queries
        if "ai_agent_knowledge_bases" in statement:
            assignment_queries += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count_assignment_query)
    try:
        listed = (await client.get("/api/v1/ai/agents", headers=headers_a)).json()["items"]
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_assignment_query)
    assignments = {agent["name"]: set(agent["knowledge_base_ids"]) for agent in listed}
    assert assignment_queries == 1
    assert assignments["Returns assistant"] == {base_a["id"], shared_base["id"]}
    assert assignments["Product assistant"] == {shared_base["id"]}

    default_deactivation = await client.post(
        f"/api/v1/ai/agents/{agents_a['items'][0]['id']}/deactivate", headers=headers_a
    )
    assert default_deactivation.status_code == 409


@pytest.mark.anyio
async def test_assignment_composite_foreign_key_rejects_cross_tenant_base(client):
    owner_a = await approved_workspace(client, "ai-fk-a")
    owner_b = await approved_workspace(client, "ai-fk-b")
    organization_a = UUID(owner_a["user"]["organization_id"])
    default_agent = (
        await client.get("/api/v1/ai/agents", headers=bearer(owner_a["access_token"]))
    ).json()["items"][0]
    foreign_base = (
        await client.get("/api/v1/knowledge/bases", headers=bearer(owner_b["access_token"]))
    ).json()["items"][0]

    async with SessionLocal() as db:
        await set_tenant_context(db, organization_a)
        db.add(
            AIAgentKnowledgeBase(
                organization_id=organization_a,
                ai_agent_id=UUID(default_agent["id"]),
                knowledge_base_id=UUID(foreign_base["id"]),
            )
        )
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()


@pytest.mark.anyio
async def test_ai_agent_audit_is_tenant_scoped_and_never_stores_instruction_text(client):
    owner = await approved_workspace(client, "agent-audit")
    other_owner = await approved_workspace(client, "agent-audit-other")
    owner_headers = bearer(owner["access_token"])
    other_headers = bearer(other_owner["access_token"])
    initial_instruction = "Unique private instruction phrase 9d2f"
    created = await client.post(
        "/api/v1/ai/agents",
        headers=owner_headers,
        json={"name": "Returns bot", "system_instructions": initial_instruction},
    )
    assert created.status_code == 201, created.text
    agent_id = created.json()["id"]

    changed_instruction = "Another private instruction phrase 1ab7"
    updated = await client.put(
        f"/api/v1/ai/agents/{agent_id}",
        headers=owner_headers,
        json={"name": "Returns assistant", "system_instructions": changed_instruction},
    )
    assert updated.status_code == 200, updated.text
    # Repeating the same settings is idempotent and must not create a false audit event.
    repeated = await client.put(
        f"/api/v1/ai/agents/{agent_id}",
        headers=owner_headers,
        json={"name": "Returns assistant", "system_instructions": changed_instruction},
    )
    assert repeated.status_code == 200, repeated.text

    audit_response = await client.get(
        f"/api/v1/ai/agents/{agent_id}/audit?limit=10", headers=owner_headers
    )
    assert audit_response.status_code == 200, audit_response.text
    audit = audit_response.json()
    assert audit["total"] == 2
    assert {item["event_type"] for item in audit["items"]} == {"created", "updated"}
    serialized_audit = audit_response.text
    assert initial_instruction not in serialized_audit
    assert changed_instruction not in serialized_audit
    updated_event = next(item for item in audit["items"] if item["event_type"] == "updated")
    assert updated_event["actor_name"] == owner["user"]["full_name"]
    assert updated_event["config_version"] == updated.json()["config_version"]

    cross_tenant = await client.get(f"/api/v1/ai/agents/{agent_id}/audit", headers=other_headers)
    assert cross_tenant.status_code == 404

    organization_id = UUID(owner["user"]["organization_id"])
    user_id = UUID(owner["user"]["id"])
    async with SessionLocal.begin() as session:
        await set_tenant_context(session, organization_id)
        member = await session.get(User, user_id)
        assert member is not None
        member.role = "viewer"
    viewer_headers = bearer(create_access_token(str(user_id), str(organization_id)))
    denied = await client.get(f"/api/v1/ai/agents/{agent_id}/audit", headers=viewer_headers)
    assert denied.status_code == 403


@pytest.mark.anyio
async def test_knowledge_configuration_enforces_owner_admin_agent_viewer_permissions(client):
    owner = await approved_workspace(client, "knowledge-viewer")
    owner_headers = bearer(owner["access_token"])
    base = (
        await client.post(
            "/api/v1/knowledge/bases", headers=owner_headers, json={"name": "Returns"}
        )
    ).json()
    uploaded = await upload_text(
        client, owner, "returns.txt", b"Returns are accepted within 30 days."
    )
    assert uploaded.status_code == 202, uploaded.text
    document_id = uploaded.json()["id"]
    organization_id = UUID(owner["user"]["organization_id"])
    user_id = UUID(owner["user"]["id"])

    async def set_role(role: str) -> dict[str, str]:
        async with SessionLocal.begin() as session:
            await set_tenant_context(session, organization_id)
            user = await session.get(User, user_id)
            assert user is not None
            user.role = role
        return bearer(create_access_token(str(user_id), str(organization_id)))

    agent_headers = await set_role("agent")
    assert (
        await client.post(
            "/api/v1/knowledge/bases", headers=agent_headers, json={"name": "Agent write"}
        )
    ).status_code == 403
    assert (
        await upload_text(
            client,
            {"access_token": agent_headers["Authorization"].removeprefix("Bearer ")},
            "agent.txt",
            b"No configuration write access",
        )
    ).status_code == 403
    assert (
        await client.post(
            "/api/v1/ai/agents",
            headers=agent_headers,
            json={"name": "Agent bot", "knowledge_base_ids": [base["id"]]},
        )
    ).status_code == 403

    admin_headers = await set_role("admin")
    admin_base = await client.post(
        "/api/v1/knowledge/bases", headers=admin_headers, json={"name": "Admin managed"}
    )
    assert admin_base.status_code == 201, admin_base.text
    admin_bot = await client.post(
        "/api/v1/ai/agents",
        headers=admin_headers,
        json={"name": "Admin managed bot", "knowledge_base_ids": [admin_base.json()["id"]]},
    )
    assert admin_bot.status_code == 201, admin_bot.text

    viewer_headers = await set_role("viewer")

    assert (await client.get("/api/v1/knowledge/bases", headers=viewer_headers)).status_code == 200
    assert (
        await client.get(f"/api/v1/knowledge/documents/{document_id}", headers=viewer_headers)
    ).status_code == 200
    assert (await client.get("/api/v1/ai/agents", headers=viewer_headers)).status_code == 200
    assert (
        await client.post(
            "/api/v1/knowledge/bases", headers=viewer_headers, json={"name": "Forbidden"}
        )
    ).status_code == 403
    assert (
        await upload_text(
            client,
            {"access_token": viewer_headers["Authorization"].removeprefix("Bearer ")},
            "viewer.txt",
            b"No write access",
        )
    ).status_code == 403
    assert (
        await client.post(
            f"/api/v1/knowledge/documents/{document_id}/reprocess", headers=viewer_headers
        )
    ).status_code == 403
    assert (
        await client.delete(f"/api/v1/knowledge/documents/{document_id}", headers=viewer_headers)
    ).status_code == 403
    assert (
        await client.post(
            "/api/v1/ai/agents",
            headers=viewer_headers,
            json={"name": "Forbidden bot", "knowledge_base_ids": [base["id"]]},
        )
    ).status_code == 403


@pytest.mark.anyio
async def test_ai_execution_retrieval_uses_only_assigned_knowledge_bases(client):
    owner = await approved_workspace(client, "ai-agent-retrieval")
    headers = bearer(owner["access_token"])
    organization_id = UUID(owner["user"]["organization_id"])
    user_id = UUID(owner["user"]["id"])
    default_base = (await client.get("/api/v1/knowledge/bases", headers=headers)).json()["items"][0]
    private_base = (
        await client.post("/api/v1/knowledge/bases", headers=headers, json={"name": "Returns"})
    ).json()
    custom = await client.post(
        "/api/v1/ai/agents",
        headers=headers,
        json={
            "name": "Returns bot",
            "system_instructions": "Follow the original returns policy wording.",
            "knowledge_base_ids": [private_base["id"]],
        },
    )
    assert custom.status_code == 201, custom.text

    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        for base_id, name, excerpt in (
            (UUID(default_base["id"]), "general.txt", "general only passage"),
            (UUID(private_base["id"]), "returns.txt", "returns policy passage"),
        ):
            document = KnowledgeDocument(
                organization_id=organization_id,
                knowledge_base_id=base_id,
                name=name,
                content_type="text/plain",
                size_bytes=30,
                status="ready",
                uploaded_by_user_id=user_id,
                content_revision=hash_document_text(excerpt),
            )
            db.add(document)
            await db.flush()
            db.add(
                DocumentChunk(
                    organization_id=organization_id,
                    document_id=document.id,
                    chunk_index=0,
                    content=excerpt,
                    content_hash=hash_chunk_text(excerpt),
                )
            )
        execution = AIExecution(
            organization_id=organization_id,
            requested_by_user_id=user_id,
            kind="playground",
            status="running",
            question="returns policy",
            ai_agent_id=UUID(custom.json()["id"]),
            ai_agent_config_version=custom.json()["config_version"],
            ai_agent_instructions_snapshot=custom.json()["system_instructions"],
        )
        db.add(execution)
        await db.flush()
        execution_id = execution.id
        await db.commit()

    loaded = await load_execution_context(organization_id, execution_id)
    assert loaded is not None
    _execution, _question, _transcript, context, citations, _outcomes, _integration = loaded
    assert [item["document_name"] for item in context] == ["returns.txt"]
    assert [item["document_name"] for item in citations] == ["returns.txt"]

    updated_agent = await client.put(
        f"/api/v1/ai/agents/{custom.json()['id']}",
        headers=headers,
        json={
            "name": "Returns bot",
            "system_instructions": "Use the newly edited returns policy wording.",
        },
    )
    assert updated_agent.status_code == 200, updated_agent.text
    loaded_after_edit = await load_execution_context(organization_id, execution_id)
    assert loaded_after_edit is not None
    assert "Follow the original returns policy wording." in loaded_after_edit[0].instructions
    assert "newly edited" not in loaded_after_edit[0].instructions

    # A job queued against the bot must resolve its current assignments when
    # the worker loads context, rather than retaining access to a removed base.
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        queued = AIExecution(
            organization_id=organization_id,
            requested_by_user_id=user_id,
            kind="playground",
            status="queued",
            question="returns policy",
            ai_agent_id=UUID(custom.json()["id"]),
            ai_agent_config_version=updated_agent.json()["config_version"],
            ai_agent_instructions_snapshot=updated_agent.json()["system_instructions"],
        )
        db.add(queued)
        await db.commit()
        queued_execution_id = queued.id

    removed = await client.put(
        f"/api/v1/ai/agents/{custom.json()['id']}/knowledge-bases",
        headers=headers,
        json={"knowledge_base_ids": []},
    )
    assert removed.status_code == 200, removed.text
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        await db.execute(
            update(AIExecution)
            .where(
                AIExecution.organization_id == organization_id,
                AIExecution.id == queued_execution_id,
            )
            .values(status="running")
        )
        await db.commit()
    queued_context = await load_execution_context(organization_id, queued_execution_id)
    assert queued_context is not None
    assert queued_context[3] == []
    assert queued_context[4] == []

    # Even a retained assignment cannot retrieve sources after a base is archived.
    restored = await client.put(
        f"/api/v1/ai/agents/{custom.json()['id']}/knowledge-bases",
        headers=headers,
        json={"knowledge_base_ids": [private_base["id"]]},
    )
    assert restored.status_code == 200, restored.text
    archived = await client.post(
        f"/api/v1/knowledge/bases/{private_base['id']}/archive", headers=headers
    )
    assert archived.status_code == 200, archived.text
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        archived_execution = AIExecution(
            organization_id=organization_id,
            requested_by_user_id=user_id,
            kind="playground",
            status="running",
            question="returns policy",
            ai_agent_id=UUID(custom.json()["id"]),
            ai_agent_config_version=updated_agent.json()["config_version"],
            ai_agent_instructions_snapshot=updated_agent.json()["system_instructions"],
        )
        db.add(archived_execution)
        await db.commit()
        archived_execution_id = archived_execution.id
    archived_context = await load_execution_context(organization_id, archived_execution_id)
    assert archived_context is not None
    assert archived_context[3] == []
    assert archived_context[4] == []

    inactive_agent = await client.post(
        "/api/v1/ai/agents",
        headers=headers,
        json={"name": "Inactive assistant", "knowledge_base_ids": [default_base["id"]]},
    )
    assert inactive_agent.status_code == 201, inactive_agent.text
    deactivated = await client.post(
        f"/api/v1/ai/agents/{inactive_agent.json()['id']}/deactivate", headers=headers
    )
    assert deactivated.status_code == 200, deactivated.text
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        inactive_execution = AIExecution(
            organization_id=organization_id,
            requested_by_user_id=user_id,
            kind="playground",
            status="running",
            question="returns policy",
            ai_agent_id=UUID(inactive_agent.json()["id"]),
            ai_agent_config_version=inactive_agent.json()["config_version"],
        )
        db.add(inactive_execution)
        await db.commit()
        inactive_execution_id = inactive_execution.id
    inactive_context = await load_execution_context(organization_id, inactive_execution_id)
    assert inactive_context is not None
    assert inactive_context[3] == []
    assert inactive_context[4] == []


@pytest.mark.anyio
async def test_hybrid_semantic_retrieval_is_tenant_and_bot_scoped(client, monkeypatch):
    from app.features.ai.application import retrieval_search
    from app.core.config import settings
    from app.features.ai.infrastructure.embedding_gateway import (
        EmbeddingProviderError,
        EmbeddingVector,
    )

    owner_a = await approved_workspace(client, "semantic-a")
    owner_b = await approved_workspace(client, "semantic-b")
    headers_a = bearer(owner_a["access_token"])
    headers_b = bearer(owner_b["access_token"])
    org_a = UUID(owner_a["user"]["organization_id"])
    org_b = UUID(owner_b["user"]["organization_id"])
    default_a = (await client.get("/api/v1/knowledge/bases", headers=headers_a)).json()["items"][0]
    default_b = (await client.get("/api/v1/knowledge/bases", headers=headers_b)).json()["items"][0]
    extra_base = await client.post(
        "/api/v1/knowledge/bases", headers=headers_a, json={"name": "Unassigned source"}
    )
    assert extra_base.status_code == 201, extra_base.text
    agents_a = (await client.get("/api/v1/ai/agents", headers=headers_a)).json()["items"]
    agent_a = next(agent for agent in agents_a if agent["is_default"])
    model = "test-embedding-model"
    monkeypatch.setattr(settings, "ai_embedding_model", model)
    monkeypatch.setattr(settings, "ai_embedding_dimensions", 3)
    monkeypatch.setattr(settings, "ai_embedding_version", "test-v1")
    monkeypatch.setattr(retrieval_search, "is_embedding_provider_configured", lambda: True)

    async def embedding_for_query(*_args, **_kwargs):
        return [EmbeddingVector([1.0, 0.0, 0.0], model, 3)]

    monkeypatch.setattr(retrieval_search, "embed_texts", embedding_for_query)
    async with SessionLocal() as db:
        await set_tenant_context(db, org_a)
        for base_id, name, excerpt in (
            (UUID(default_a["id"]), "selected.txt", "Refunds are available within fourteen days."),
            (
                UUID(extra_base.json()["id"]),
                "unassigned.txt",
                "Refunds are available in thirty days.",
            ),
        ):
            document = KnowledgeDocument(
                organization_id=org_a,
                knowledge_base_id=base_id,
                name=name,
                content_type="text/plain",
                size_bytes=len(excerpt),
                status="ready",
                uploaded_by_user_id=UUID(owner_a["user"]["id"]),
                content_revision=hash_document_text(excerpt),
            )
            db.add(document)
            await db.flush()
            chunk = DocumentChunk(
                organization_id=org_a,
                document_id=document.id,
                chunk_index=0,
                content=excerpt,
                content_hash=hash_chunk_text(excerpt),
            )
            db.add(chunk)
            await db.flush()
            db.add(
                DocumentEmbedding(
                    organization_id=org_a,
                    document_id=document.id,
                    chunk_index=0,
                    embedding_model=model,
                    embedding_version="test-v1",
                    dimensions=3,
                    embedding=[1.0, 0.0, 0.0],
                )
            )
        await db.commit()

    async with SessionLocal() as db:
        await set_tenant_context(db, org_b)
        excerpt = "Refunds are available within fourteen days."
        document = KnowledgeDocument(
            organization_id=org_b,
            knowledge_base_id=UUID(default_b["id"]),
            name="other-tenant.txt",
            content_type="text/plain",
            size_bytes=len(excerpt),
            status="ready",
            uploaded_by_user_id=UUID(owner_b["user"]["id"]),
            content_revision=hash_document_text(excerpt),
        )
        db.add(document)
        await db.flush()
        db.add(
            DocumentChunk(
                organization_id=org_b,
                document_id=document.id,
                chunk_index=0,
                content=excerpt,
                content_hash=hash_chunk_text(excerpt),
            )
        )
        await db.flush()
        db.add(
            DocumentEmbedding(
                organization_id=org_b,
                document_id=document.id,
                chunk_index=0,
                embedding_model=model,
                embedding_version="test-v1",
                dimensions=3,
                embedding=[1.0, 0.0, 0.0],
            )
        )
        await db.commit()

    async with SessionLocal() as db:
        await set_tenant_context(db, org_a)
        result = await retrieval_search.search_agent_knowledge(
            db,
            organization_id=org_a,
            ai_agent_id=UUID(agent_a["id"]),
            search_text="What if my purchase is not right for me?",
        )
        assert result.retrieval_method == "semantic"
        assert result.semantic_candidate_count == 1
        assert [match.document_name for match in result.matches] == ["selected.txt"]
        assert result.matches[0].semantic_similarity == pytest.approx(1.0)

        async def provider_failure(*_args, **_kwargs):
            raise EmbeddingProviderError("embedding_provider_http_503", retryable=True)

        monkeypatch.setattr(retrieval_search, "embed_texts", provider_failure)
        fallback = await retrieval_search.search_agent_knowledge(
            db,
            organization_id=org_a,
            ai_agent_id=UUID(agent_a["id"]),
            search_text="refunds fourteen days",
        )
        assert fallback.retrieval_method == "keyword"
        assert fallback.embedding_status == "embedding_provider_http_503"
        assert [match.document_name for match in fallback.matches] == ["selected.txt"]
