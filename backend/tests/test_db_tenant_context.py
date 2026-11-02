from uuid import uuid4

import pytest

from app.db.session import set_tenant_context


@pytest.mark.anyio
async def test_tenant_context_is_set_transaction_locally():
    organization_id = uuid4()
    calls = []

    class SessionStub:
        async def execute(self, statement, parameters):
            calls.append((str(statement), parameters))

    await set_tenant_context(SessionStub(), organization_id)

    assert len(calls) == 1
    statement, parameters = calls[0]
    assert "set_config('app.current_tenant', :tenant_id, true)" in statement
    assert parameters == {"tenant_id": str(organization_id)}
