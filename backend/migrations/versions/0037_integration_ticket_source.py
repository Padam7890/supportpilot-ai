"""Allow provider-neutral integration conversations to create tickets."""

import sqlalchemy as sa
from alembic import op

revision = "0037_integration_ticket_source"
down_revision = "0036_knowledge_bases_and_ai_agents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_tickets_source", "tickets", type_="check")
    op.create_check_constraint(
        "ck_tickets_source",
        "tickets",
        "source IN ('manual', 'shopify_widget', 'integration')",
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM tickets WHERE source = 'integration') THEN
                RAISE EXCEPTION 'Cannot downgrade while integration-source tickets exist';
            END IF;
            END $$;"""
        )
    )
    op.drop_constraint("ck_tickets_source", "tickets", type_="check")
    op.create_check_constraint(
        "ck_tickets_source", "tickets", "source IN ('manual', 'shopify_widget')"
    )
