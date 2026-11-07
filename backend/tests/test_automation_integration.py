import asyncio
import os
import statistics
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal, set_tenant_context
from app.models import AutomationExecution, Ticket
from app.workers.application.dispatcher import WorkerDispatcher
from app.workers.handlers.automation import AutomationExecutionHandler
from app.workers.infrastructure.job_repository import DurableJobRepository
from tests.test_widget_integration import bearer, setup_widget

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Automation integration tests require isolated PostgreSQL",
)


@pytest.mark.anyio
async def test_published_priority_automation_runs_once_for_customer_message(client):
    auth, organization_id, public_id = await setup_widget(
        client, "automation-run", "https://automation-run.example"
    )
    headers = bearer(auth["access_token"])
    created = await client.post(
        "/api/v1/automations",
        headers=headers,
        json={
            "name": "Prioritize refund requests",
            "description": "Raise priority on refund questions",
            "definition": {
                "trigger": "customer_message_received",
                "conditions": [{"kind": "contains_keyword", "value": "refund"}],
                "actions": [{"kind": "set_priority", "value": "urgent"}],
            },
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["canvas_layout"] == {
        "trigger": {"x": 400, "y": 48},
        "conditions": [{"x": 370, "y": 154}],
        "actions": [{"x": 370, "y": 312}],
    }
    workflow_id = created.json()["id"]
    preview = await client.post(
        "/api/v1/automations/preview",
        headers=headers,
        json={
            "definition": created.json()["definition"],
            "sample_message": "I need a refund",
        },
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["matches"] is True
    assert preview.json()["planned_actions"] == [
        {
            "kind": "set_priority",
            "summary": "Set ticket priority to urgent",
            "outcome": "would_run",
            "detail": None,
        },
    ]
    assert (await client.get("/api/v1/automations/metrics", headers=headers)).json()["total"] == 0
    published = await client.post(
        f"/api/v1/automations/{workflow_id}/publish", headers=headers
    )
    assert published.status_code == 200, published.text
    assert published.json()["version"] == 1

    incoming = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={"Origin": "https://automation-run.example", "Idempotency-Key": "automation-message-key-0001"},
        json={"content": "I need a refund"},
    )
    assert incoming.status_code == 201, incoming.text
    duplicate = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={"Origin": "https://automation-run.example", "Idempotency-Key": "automation-message-key-0001"},
        json={"content": "I need a refund"},
    )
    assert duplicate.status_code == 201

    worker = AutomationExecutionHandler()
    job = await worker.claim(organization_id)
    assert job is not None
    assert job.claim_token is not None
    replacement_token = uuid4()
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        execution = await db.scalar(
            select(AutomationExecution).where(AutomationExecution.id == job.job_id)
        )
        assert execution is not None
        execution.lease_token = replacement_token
        await db.commit()

    # A reclaimed execution fences off the original worker, even if it resumes late.
    await worker.process(job)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        ticket = await db.scalar(select(Ticket).where(Ticket.id == incoming.json()["ticket_id"]))
        execution = await db.scalar(
            select(AutomationExecution).where(AutomationExecution.id == job.job_id)
        )
        assert execution is not None and execution.status == "running"
    assert ticket is not None and ticket.priority != "urgent"

    fresh_job = replace(job, claim_token=replacement_token)
    await worker.process(fresh_job)
    await worker.process(fresh_job)

    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        ticket = await db.scalar(select(Ticket).where(Ticket.id == incoming.json()["ticket_id"]))
        executions = list(
            await db.scalars(
                select(AutomationExecution).where(
                    AutomationExecution.organization_id == organization_id,
                    AutomationExecution.workflow_id == workflow_id,
                )
            )
        )
    assert ticket is not None and ticket.priority == "urgent"
    assert len(executions) == 1
    assert executions[0].status == "succeeded"
    assert executions[0].attempt_count == 1
    assert executions[0].result[0]["outcome"] == "applied"

    edited = await client.patch(
        f"/api/v1/automations/{workflow_id}",
        headers=headers,
        json={
            "definition": {
                "trigger": "customer_message_received",
                "conditions": [{"kind": "contains_keyword", "value": "refund"}],
                "actions": [{"kind": "set_priority", "value": "low"}],
            }
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["status"] == "active"
    assert edited.json()["has_unpublished_changes"] is True
    assert edited.json()["published_version"] == 1
    assert edited.json()["draft_version"] == 2
    republished = await client.post(
        f"/api/v1/automations/{workflow_id}/publish", headers=headers
    )
    assert republished.status_code == 200, republished.text
    assert republished.json()["version"] == 2
    history = await client.get(
        f"/api/v1/automations/{workflow_id}/executions", headers=headers
    )
    assert history.status_code == 200, history.text
    assert history.json()[0]["version"] == 1


@pytest.mark.anyio
async def test_workflow_and_execution_history_are_isolated_by_workspace(client):
    auth_a, _org_a, _widget_a = await setup_widget(
        client, "automation-tenant-a", "https://automation-a.example"
    )
    auth_b, _org_b, _widget_b = await setup_widget(
        client, "automation-tenant-b", "https://automation-b.example"
    )
    created = await client.post(
        "/api/v1/automations",
        headers=bearer(auth_a["access_token"]),
        json={
            "name": f"Private {uuid4().hex[:6]}",
            "definition": {
                "trigger": "customer_message_received",
                "actions": [{"kind": "set_priority", "value": "high"}],
            },
        },
    )
    assert created.status_code == 201
    response = await client.get("/api/v1/automations", headers=bearer(auth_b["access_token"]))
    assert response.status_code == 200
    assert all(row["id"] != created.json()["id"] for row in response.json())
    foreign_target_preview = await client.post(
        "/api/v1/automations/preview",
        headers=bearer(auth_a["access_token"]),
        json={
            "definition": {
                "trigger": "customer_message_received",
                "actions": [{"kind": "assign_to_user", "user_id": auth_b["user"]["id"]}],
            },
            "sample_message": "Please help",
        },
    )
    assert foreign_target_preview.status_code == 422


@pytest.mark.anyio
async def test_workflow_version_restore_creates_new_draft_without_rewriting_history(client):
    auth, _organization_id, _widget_id = await setup_widget(
        client, "automation-restore", "https://automation-restore.example"
    )
    headers = bearer(auth["access_token"])
    created = await client.post(
        "/api/v1/automations",
        headers=headers,
        json={
            "name": "Versioned restore",
            "definition": {
                "trigger": "customer_message_received",
                "conditions": [{"kind": "contains_keyword", "value": "refund"}],
                "actions": [{"kind": "set_priority", "value": "high"}],
            },
            "canvas_layout": {
                "trigger": {"x": 80, "y": 18},
                "conditions": [{"x": 130, "y": 210}],
                "actions": [{"x": 540, "y": 410}],
            },
        },
    )
    assert created.status_code == 201, created.text
    first_layout = created.json()["canvas_layout"]
    workflow_id = created.json()["id"]
    first = await client.post(f"/api/v1/automations/{workflow_id}/publish", headers=headers)
    assert first.status_code == 200

    updated = await client.patch(
        f"/api/v1/automations/{workflow_id}",
        headers=headers,
        json={
            "definition": {
                "trigger": "customer_message_received",
                "conditions": [{"kind": "contains_keyword", "value": "shipping"}],
                "actions": [{"kind": "set_priority", "value": "urgent"}],
            },
            "canvas_layout": {
                "trigger": {"x": 120, "y": 32},
                "conditions": [{"x": 600, "y": 260}],
                "actions": [{"x": 130, "y": 480}],
            },
        },
    )
    assert updated.status_code == 200
    second = await client.post(f"/api/v1/automations/{workflow_id}/publish", headers=headers)
    assert second.status_code == 200
    assert second.json()["version"] == 2

    history = await client.get(f"/api/v1/automations/{workflow_id}/versions", headers=headers)
    assert history.status_code == 200, history.text
    assert [item["version"] for item in history.json()] == [2, 1]
    assert [item["is_current"] for item in history.json()] == [True, False]

    restored = await client.post(
        f"/api/v1/automations/{workflow_id}/versions/1/restore", headers=headers
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["restored_from_version"] == 1
    restored_workflow = restored.json()["workflow"]
    assert restored_workflow["status"] == "active"
    assert restored_workflow["published_version"] == 2
    assert restored_workflow["draft_version"] == 3
    assert restored_workflow["has_unpublished_changes"] is True
    assert restored_workflow["definition"]["conditions"][0]["value"] == "refund"
    assert restored_workflow["canvas_layout"] == first_layout

    versions_after_restore = await client.get(
        f"/api/v1/automations/{workflow_id}/versions", headers=headers
    )
    assert [item["version"] for item in versions_after_restore.json()] == [2, 1]
    published_restore = await client.post(
        f"/api/v1/automations/{workflow_id}/publish", headers=headers
    )
    assert published_restore.status_code == 200
    assert published_restore.json()["version"] == 3


@pytest.mark.anyio
async def test_workflow_version_history_and_restore_are_tenant_scoped(client):
    auth_a, _org_a, _widget_a = await setup_widget(
        client, "automation-version-owner", "https://automation-version-owner.example"
    )
    auth_b, _org_b, _widget_b = await setup_widget(
        client, "automation-version-other", "https://automation-version-other.example"
    )
    created = await client.post(
        "/api/v1/automations",
        headers=bearer(auth_a["access_token"]),
        json={
            "name": "Private versions",
            "definition": {
                "trigger": "customer_message_received",
                "actions": [{"kind": "set_priority", "value": "high"}],
            },
        },
    )
    assert created.status_code == 201
    workflow_id = created.json()["id"]
    assert (await client.post(
        f"/api/v1/automations/{workflow_id}/publish",
        headers=bearer(auth_a["access_token"]),
    )).status_code == 200

    other_headers = bearer(auth_b["access_token"])
    history = await client.get(f"/api/v1/automations/{workflow_id}/versions", headers=other_headers)
    restore = await client.post(
        f"/api/v1/automations/{workflow_id}/versions/1/restore", headers=other_headers
    )
    assert history.status_code == 404
    assert restore.status_code == 404


@pytest.mark.anyio
async def test_expired_final_lease_is_failed_and_visible_in_history_and_metrics(client):
    auth, organization_id, public_id = await setup_widget(
        client, "automation-crash", "https://automation-crash.example"
    )
    headers = bearer(auth["access_token"])
    created = await client.post(
        "/api/v1/automations",
        headers=headers,
        json={
            "name": "Crash recovery visibility",
            "definition": {
                "trigger": "customer_message_received",
                "actions": [{"kind": "set_priority", "value": "high"}],
            },
        },
    )
    assert created.status_code == 201, created.text
    workflow_id = created.json()["id"]
    published = await client.post(
        f"/api/v1/automations/{workflow_id}/publish", headers=headers
    )
    assert published.status_code == 200, published.text

    incoming = await client.post(
        f"/api/v1/widget/{public_id}/messages",
        headers={
            "Origin": "https://automation-crash.example",
            "Idempotency-Key": "automation-crash-message-0001",
        },
        json={"content": "Please help"},
    )
    assert incoming.status_code == 201, incoming.text

    # Simulate a process crash after claiming its final permitted attempt.
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        execution = await db.scalar(
            select(AutomationExecution).where(
                AutomationExecution.organization_id == organization_id,
                AutomationExecution.workflow_id == workflow_id,
            )
        )
        assert execution is not None
        execution.status = "running"
        execution.attempt_count = execution.max_attempts
        execution.lease_token = uuid4()
        execution.locked_until = datetime.now(UTC) - timedelta(seconds=1)
        execution.error_code = None
        execution.completed_at = None
        await db.commit()

    assert await AutomationExecutionHandler().claim(organization_id) is None

    history = await client.get(
        f"/api/v1/automations/{workflow_id}/executions", headers=headers
    )
    assert history.status_code == 200, history.text
    failed = history.json()[0]
    assert failed["status"] == "failed"
    assert failed["attempt_count"] == 3
    assert failed["error_code"] == "automation_execution_failed"
    assert failed["correlation_id"]
    assert failed["completed_at"] is not None

    metrics = await client.get("/api/v1/automations/metrics", headers=headers)
    assert metrics.status_code == 200, metrics.text
    assert metrics.json()["failed"] == 1
    assert sum(point["total"] for point in metrics.json()["daily"]) == 1
    assert sum(point["failed"] for point in metrics.json()["daily"]) == 1
    assert len(metrics.json()["daily"]) in {30, 31}
    assert metrics.json()["top_errors"] == [
        {"code": "automation_execution_failed", "count": 1}
    ]

    today = datetime.now(UTC).date().isoformat()
    ranged_metrics = await client.get(
        f"/api/v1/automations/metrics?start_date={today}&end_date={today}",
        headers=headers,
    )
    assert ranged_metrics.status_code == 200, ranged_metrics.text
    assert ranged_metrics.json()["failed"] == 1
    assert ranged_metrics.json()["daily"] == [
        {
            "date": today,
            "total": 1,
            "succeeded": 0,
            "failed": 1,
            "queued": 0,
            "running": 0,
        }
    ]
    assert ranged_metrics.json()["top_errors"] == [
        {"code": "automation_execution_failed", "count": 1}
    ]
    reversed_range = await client.get(
        f"/api/v1/automations/metrics?start_date={today}&end_date=2020-01-01",
        headers=headers,
    )
    assert reversed_range.status_code == 422


@pytest.mark.anyio
@pytest.mark.parametrize("messages_per_tenant", [4, 12], ids=["12-jobs", "36-jobs"])
async def test_concurrent_dispatchers_process_tenant_jobs_once(client, messages_per_tenant):
    """Measure parallel durable claims and assert tenant-scoped jobs are not duplicated."""
    organizations: list[tuple[str, str, str, str]] = []
    expected_execution_ids: set[str] = set()

    for tenant_number in range(3):
        label = f"automation-load-{tenant_number}-{uuid4().hex[:6]}"
        origin = f"https://{label}.example"
        auth, organization_id, public_id = await setup_widget(client, label, origin)
        headers = bearer(auth["access_token"])
        created = await client.post(
            "/api/v1/automations",
            headers=headers,
            json={
                "name": "Load test priority workflow",
                "definition": {
                    "trigger": "customer_message_received",
                    "actions": [{"kind": "set_priority", "value": "high"}],
                },
            },
        )
        assert created.status_code == 201, created.text
        published = await client.post(
            f"/api/v1/automations/{created.json()['id']}/publish", headers=headers
        )
        assert published.status_code == 200, published.text

        first = await client.post(
            f"/api/v1/widget/{public_id}/messages",
            headers={"Origin": origin, "Idempotency-Key": f"load-{label}-0"},
            json={"content": "First load-test message"},
        )
        assert first.status_code == 201, first.text
        visitor_headers = {
            "Origin": origin,
            "Authorization": f"Bearer {first.json()['visitor_token']}",
        }
        for message_number in range(1, messages_per_tenant):
            followup = await client.post(
                f"/api/v1/widget/conversations/{first.json()['conversation_id']}/messages",
                headers={
                    **visitor_headers,
                    "Idempotency-Key": f"load-{label}-{message_number}",
                },
                json={"content": f"Load-test message {message_number}"},
            )
            assert followup.status_code == 200, followup.text

        organizations.append((label, str(organization_id), created.json()["id"], origin))

    async with SessionLocal() as db:
        for _label, organization_id, workflow_id, _origin in organizations:
            await set_tenant_context(db, organization_id)
            rows = list(
                await db.scalars(
                    select(AutomationExecution.id).where(
                        AutomationExecution.organization_id == organization_id,
                        AutomationExecution.workflow_id == workflow_id,
                    )
                )
            )
            assert len(rows) == messages_per_tenant
            expected_execution_ids.update(str(row) for row in rows)
            await db.rollback()

    benchmark_organization_ids = sorted(
        UUID(organization_id) for _label, organization_id, _workflow_id, _origin in organizations
    )

    class BenchmarkJobRepository(DurableJobRepository):
        async def approved_organizations(self, after: UUID | None = None) -> list[UUID]:
            return [
                organization_id
                for organization_id in benchmark_organization_ids
                if after is None or organization_id > after
            ]

    handler_latencies: list[float] = []

    class TimedAutomationExecutionHandler(AutomationExecutionHandler):
        async def process(self, job):
            process_started = time.perf_counter()
            try:
                await super().process(job)
            finally:
                handler_latencies.append(time.perf_counter() - process_started)

    handler = TimedAutomationExecutionHandler()

    dispatchers = [
        WorkerDispatcher(
            handlers=(handler,),
            repository=BenchmarkJobRepository(),
        )
        for _ in range(6)
    ]
    start = time.perf_counter()
    processed = await asyncio.gather(
        *(dispatcher.dispatch_one() for dispatcher in dispatchers)
    )

    # Drain any remaining work serially; the concurrent wave must not lose jobs.
    drainer = dispatchers[0]
    drained_count = 0
    while await drainer.dispatch_one():
        drained_count += 1
    elapsed_seconds = time.perf_counter() - start

    actual_rows = []
    for _label, organization_id, workflow_id, _origin in organizations:
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            actual_rows.extend(
                list(
                    await db.scalars(
                        select(AutomationExecution).where(
                            AutomationExecution.organization_id == organization_id,
                            AutomationExecution.workflow_id == workflow_id,
                        )
                    )
                )
            )
    actual_ids = {str(row.id) for row in actual_rows}
    expected_count = len(organizations) * messages_per_tenant
    assert actual_ids == expected_execution_ids
    assert len(actual_rows) == expected_count
    assert all(row.status == "succeeded" for row in actual_rows)
    assert all(row.attempt_count == 1 for row in actual_rows)
    assert all(row.lease_token is None and row.locked_until is None for row in actual_rows)
    assert sum(processed) == len(dispatchers)
    assert elapsed_seconds > 0
    print(
        "automation_worker_load "
        f"jobs={len(actual_rows)} tenants={len(organizations)} "
        f"messages_per_tenant={messages_per_tenant} "
        f"concurrent_claims={sum(processed)} drained={drained_count} "
        f"elapsed_seconds={elapsed_seconds:.4f} "
        f"jobs_per_second={len(actual_rows) / elapsed_seconds:.2f} "
        f"handler_p50_ms={statistics.median(handler_latencies) * 1000:.2f} "
        f"handler_p95_ms={statistics.quantiles(handler_latencies, n=20)[18] * 1000:.2f}"
    )
