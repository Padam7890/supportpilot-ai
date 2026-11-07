"""Allow supported inbound connections to select a tenant AI bot."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0059_integration_ai_bot_routing"
down_revision = "0058_first_response_sla_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "integration_connections",
        sa.Column("ai_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_integration_connections_org_ai_agent",
        "integration_connections",
        "ai_agents",
        ["organization_id", "ai_agent_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "ck_integration_connection_audits_event_type",
        "integration_connection_audits",
        type_="check",
    )
    op.create_check_constraint(
        "ck_integration_connection_audits_event_type",
        "integration_connection_audits",
        "event_type IN ('connected', 'reauthorized', 'disconnected', 'bot_routing_changed')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    routing_events = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM integration_connection_audits "
            "WHERE event_type = 'bot_routing_changed')"
        )
    ).scalar_one()
    if routing_events:
        raise RuntimeError(
            "Cannot downgrade integration bot routing while routing audit history exists"
        )

    op.drop_constraint(
        "ck_integration_connection_audits_event_type",
        "integration_connection_audits",
        type_="check",
    )
    op.create_check_constraint(
        "ck_integration_connection_audits_event_type",
        "integration_connection_audits",
        "event_type IN ('connected', 'reauthorized', 'disconnected')",
    )
    op.drop_constraint(
        "fk_integration_connections_org_ai_agent",
        "integration_connections",
        type_="foreignkey",
    )
    op.drop_column("integration_connections", "ai_agent_id")
