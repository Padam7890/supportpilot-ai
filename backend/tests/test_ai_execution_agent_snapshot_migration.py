from pathlib import Path


def test_ai_execution_agent_snapshot_migration_is_additive():
    migration = (
        Path(__file__).parents[1]
        / "migrations/versions/0040_ai_execution_agent_snapshot.py"
    ).read_text()

    assert 'revision = "0040_ai_execution_agent_snapshot"' in migration
    assert 'down_revision = "0039_ai_agent_audit"' in migration
    assert 'sa.Column("ai_agent_instructions_snapshot", sa.Text(), nullable=True)' in migration
    assert "Cannot downgrade AI execution snapshots while records exist" in migration
    assert 'op.drop_column("ai_executions", "ai_agent_instructions_snapshot")' in migration
