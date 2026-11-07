from pathlib import Path


def test_ai_agent_audit_migration_is_tenant_scoped_and_reversible():
    migration = (
        Path(__file__).parents[1] / "migrations/versions/0039_ai_agent_audit.py"
    ).read_text()

    assert 'revision = "0039_ai_agent_audit"' in migration
    assert 'down_revision = "0038_automation_foundation"' in migration
    assert '"ai_agent_audits"' in migration
    assert "fk_ai_agent_audits_org_agent" in migration
    assert "fk_ai_agent_audits_org_actor" in migration
    assert "ck_ai_agent_audits_event_type" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "app.current_tenant" in migration
    assert 'DROP POLICY IF EXISTS tenant_isolation ON "ai_agent_audits"' in migration
    assert "Cannot downgrade AI agent audit history while records exist" in migration
    assert 'op.drop_table("ai_agent_audits")' in migration
