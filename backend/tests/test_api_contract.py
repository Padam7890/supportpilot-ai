import pytest


@pytest.mark.anyio
async def test_liveness(client):
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


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
    problem_response = spec["paths"]["/api/v1/inbox"]["get"]["responses"]["401"]
    assert problem_response["content"]["application/problem+json"]["schema"]["$ref"] == (
        "#/components/schemas/ProblemDetails"
    )
    assert "application/json" not in problem_response["content"]
