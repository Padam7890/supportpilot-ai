import pytest


@pytest.mark.anyio
async def test_liveness(client):
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


@pytest.mark.anyio
async def test_customer_api_requires_auth(client):
    response = await client.get("/api/v1/customers")
    assert response.status_code == 403 or response.status_code == 401
