import logging

import pytest
from starlette.requests import Request


@pytest.mark.anyio
async def test_liveness(client):
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert response.headers.get("x-correlation-id")


@pytest.mark.anyio
async def test_worker_health_reports_only_heartbeat_count(client, monkeypatch):
    from app.main import app

    monkeypatch.setattr("app.main.active_worker_count", lambda _redis: _resolved(2))
    app.state.redis = object()
    active = await client.get("/health/worker")
    assert active.status_code == 200
    assert active.json()["status"] == "active"
    assert active.json()["active_workers"] == 2

    monkeypatch.setattr("app.main.active_worker_count", lambda _redis: _resolved(0))
    inactive = await client.get("/health/worker")
    assert inactive.status_code == 200
    assert inactive.json()["status"] == "inactive"
    assert inactive.json()["active_workers"] == 0


async def _resolved(value):
    return value


@pytest.mark.anyio
async def test_correlation_id_is_validated_and_returned(client):
    accepted = await client.get("/health/live", headers={"X-Correlation-ID": "trace_safe-001"})
    assert accepted.headers["x-correlation-id"] == "trace_safe-001"

    rejected = await client.get("/health/live", headers={"X-Correlation-ID": "unsafe trace"})
    assert rejected.headers["x-correlation-id"] != "unsafe trace"
    assert len(rejected.headers["x-correlation-id"]) == 36


@pytest.mark.anyio
async def test_unexpected_api_errors_log_correlation_id_without_returning_exception(caplog, monkeypatch):
    from app.main import app, handle_unexpected_error

    monkeypatch.setattr("app.main.current_correlation_id", lambda: "inbox-trace-123")
    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/v1/conversations/conversation-id/messages",
        "headers": [],
        "query_string": b"",
        "server": ("test", 80),
        "client": ("test", 1234),
        "scheme": "http",
        "http_version": "1.1",
        "app": app,
    })

    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = await handle_unexpected_error(request, RuntimeError("private provider details"))

    assert response.status_code == 500
    assert "private provider details" not in response.body.decode()
    error_record = next(record for record in caplog.records if record.message == "unhandled_api_error")
    assert error_record.correlation_id == "inbox-trace-123"
    assert error_record.method == "GET"


@pytest.mark.anyio
async def test_readiness_reports_database_migration_drift(client, monkeypatch):
    from app.core.database import DatabaseSchemaOutOfDate
    from app.main import app

    class RedisStub:
        async def ping(self):
            return True

    async def stale_schema():
        raise DatabaseSchemaOutOfDate("stale")

    monkeypatch.setattr("app.main.check_database", stale_schema)
    app.state.redis = RedisStub()
    try:
        response = await client.get("/health/ready")
    finally:
        del app.state.redis
    assert response.status_code == 503
    assert "Apply the latest Alembic migrations" in response.json()["detail"]


@pytest.mark.anyio
async def test_customer_api_requires_auth(client):
    response = await client.get("/api/v1/customers")
    assert response.status_code == 403 or response.status_code == 401


@pytest.mark.anyio
async def test_validation_errors_use_problem_details(client):
    response = await client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == "urn:supportpilot:problem:validation_error"
    assert body["title"] == "Unprocessable Content"
    assert body["status"] == 422
    assert body["detail"] == "Request validation failed"
    assert body["instance"] == "/api/v1/auth/login"
    assert body["code"] == "validation_error"
    assert body["errors"]


@pytest.mark.anyio
async def test_openapi_documents_versioned_inbox_and_problem_contract(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert "/api/v1/inbox" in spec["paths"]
    assert "ProblemDetails" in spec["components"]["schemas"]
    assert "InboxPage" in spec["components"]["schemas"]
    inbox_parameters = {
        parameter["name"]: parameter
        for parameter in spec["paths"]["/api/v1/inbox"]["get"]["parameters"]
    }
    assert inbox_parameters["needs_approval"]["schema"]["type"] == "boolean"
    assert inbox_parameters["unread_only"]["schema"]["type"] == "boolean"
    problem_response = spec["paths"]["/api/v1/inbox"]["get"]["responses"]["401"]
    assert problem_response["content"]["application/problem+json"]["schema"]["$ref"] == (
        "#/components/schemas/ProblemDetails"
    )
    assert "application/json" not in problem_response["content"]


@pytest.mark.anyio
async def test_feature_migration_preserves_public_route_paths(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    expected = {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/me",
        "/api/v1/organization",
        "/api/v1/customers",
        "/api/v1/customers/{customer_id}/tickets",
        "/api/v1/tickets",
        "/api/v1/tickets/{ticket_id}/conversations",
        "/api/v1/conversations/{conversation_id}/messages",
        "/api/v1/inbox",
        "/api/v1/analytics/ai-usage",
        "/api/v1/analytics/integration-deliveries",
        "/api/v1/analytics/recommendations",
        "/api/v1/integrations/widget",
        "/api/v1/widget/{public_id}/config",
        "/api/v1/widget/{public_id}/messages",
        "/api/v1/widget/conversations/{conversation_id}/messages",
    }

    assert expected <= paths.keys()
    assert "/health/worker" in paths


@pytest.mark.anyio
async def test_workspace_auth_contract_supports_slug_free_staged_login(client):
    response = await client.get("/openapi.json")
    paths = response.json()["paths"]
    assert "/api/v1/auth/login/select-workspace" in paths
    assert "/api/v1/auth/login/verify-code" in paths
    assert "/api/v1/auth/resend-code" in paths
    assert "/api/v1/auth/register/verify-email" in paths
    assert "/api/v1/auth/password-reset/request" in paths
    login = paths["/api/v1/auth/login"]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]
    login_schema = response.json()["components"]["schemas"][login["$ref"].split("/")[-1]]
    assert "email" in login_schema["required"]
    assert "password" in login_schema["required"]
    assert "organization_slug" not in login_schema["required"]
    assert login_schema["properties"]["organization_slug"]["deprecated"] is True


@pytest.mark.anyio
async def test_openapi_documents_tenant_integration_management_contract(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    paths = spec["paths"]
    assert "/api/v1/integrations/providers" in paths
    assert "/api/v1/integrations/connections" in paths
    assert "/api/v1/integrations/connections/{connection_id}" in paths
    assert "/api/v1/integrations/connections/{connection_id}/events" in paths
    assert "/api/v1/integrations/connections/{connection_id}/deliveries" in paths
    assert "/api/v1/integrations/connections/{connection_id}/disconnect" in paths
    assert "/api/v1/catalog/sync-jobs" in paths
    assert "/api/v1/catalog/sync-jobs/{job_id}" in paths
    schema = spec["components"]["schemas"]["IntegrationConnectionOut"]["properties"]
    assert "safe_configuration" in schema
    assert not any("token" in field or "credential" in field for field in schema)
    event_schema = spec["components"]["schemas"]["IntegrationWebhookEventOut"]["properties"]
    delivery_schema = spec["components"]["schemas"]["IntegrationDeliveryOut"]["properties"]
    assert "normalized_payload" not in event_schema
    assert "payload" not in event_schema
    assert "content" not in delivery_schema


@pytest.mark.anyio
async def test_openapi_documents_safe_automation_preview_contract(client):
    response = await client.get("/openapi.json")
    spec = response.json()
    path = "/api/v1/automations/preview"
    assert path in spec["paths"]
    request_ref = spec["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    response_ref = spec["paths"][path]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert request_ref.endswith("/AutomationPreviewRequest")
    assert response_ref.endswith("/AutomationPreviewOut")


@pytest.mark.anyio
async def test_provider_catalog_advertises_only_implemented_shopify_capabilities(client):
    response = await client.get("/api/v1/integrations/providers")
    assert response.status_code == 200
    assert response.json() == [
        {
            "provider_id": "shopify",
            "display_name": "Shopify",
            "version": "1",
            "capabilities": ["commerce", "product_catalog", "webhooks"],
        }
    ]
