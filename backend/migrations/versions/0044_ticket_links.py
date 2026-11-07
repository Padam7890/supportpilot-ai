"""Add tenant-scoped non-destructive links between tickets."""

import sqlalchemy as sa
from alembic import op

revision = "0044_ticket_links"
down_revision = "0043_widget_multiple_ai_agents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_low_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_high_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "ticket_low_id < ticket_high_id",
            name="ck_ticket_links_canonical_order",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_ticket_links_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "ticket_low_id"],
            ["tickets.organization_id", "tickets.id"],
            name="fk_ticket_links_org_low_ticket",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "ticket_high_id"],
            ["tickets.organization_id", "tickets.id"],
            name="fk_ticket_links_org_high_ticket",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_ticket_links_org_creator",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ticket_links"),
        sa.UniqueConstraint(
            "organization_id",
            "ticket_low_id",
            "ticket_high_id",
            name="uq_ticket_links_org_pair",
        ),
    )
    op.create_index(
        "ix_ticket_links_org_low_created",
        "ticket_links",
        ["organization_id", "ticket_low_id", "created_at"],
    )
    op.create_index(
        "ix_ticket_links_org_high_created",
        "ticket_links",
        ["organization_id", "ticket_high_id", "created_at"],
    )
    op.execute('ALTER TABLE "ticket_links" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "ticket_links" FORCE ROW LEVEL SECURITY')
    op.execute(
        """CREATE POLICY tenant_isolation ON ticket_links
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"""
    )


def downgrade() -> None:
    op.execute(
        """DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM ticket_links LIMIT 1) THEN
                RAISE EXCEPTION 'Cannot remove ticket links while related-ticket records exist';
            END IF;
        END $$"""
    )
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "ticket_links"')
    op.drop_index("ix_ticket_links_org_high_created", table_name="ticket_links")
    op.drop_index("ix_ticket_links_org_low_created", table_name="ticket_links")
    op.drop_table("ticket_links")
