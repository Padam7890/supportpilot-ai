"""Add short-lived shopper email verification records for order lookups."""

import sqlalchemy as sa
from alembic import op

revision = "0019_widget_order_verification"
down_revision = "0018_widget_ai_replies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "widget_order_verifications",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("widget_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("order_number", sa.String(60), nullable=False),
        sa.Column("shopify_order_id", sa.String(180), nullable=False),
        sa.Column("customer_email_encrypted", sa.Text(), nullable=False),
        sa.Column("code_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "widget_id"],
            ["support_widgets.organization_id", "support_widgets.id"],
            name="fk_widget_order_verifications_org_widget",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "conversation_id"],
            ["conversations.organization_id", "conversations.id"],
            name="fk_widget_order_verifications_org_conversation",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'verified', 'expired', 'locked')",
            name="ck_widget_order_verification_status",
        ),
        sa.CheckConstraint("attempt_count BETWEEN 0 AND 5", name="ck_widget_order_verification_attempts"),
    )
    op.create_index(
        "ix_widget_order_verifications_lookup",
        "widget_order_verifications",
        ["organization_id", "conversation_id", "status", "expires_at"],
    )
    op.execute("ALTER TABLE widget_order_verifications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE widget_order_verifications FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY tenant_isolation ON widget_order_verifications
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"""
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON widget_order_verifications")
    op.drop_index("ix_widget_order_verifications_lookup", table_name="widget_order_verifications")
    op.drop_table("widget_order_verifications")
