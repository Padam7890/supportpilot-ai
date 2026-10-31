import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("full_name", sa.String(160), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(30), nullable=False, server_default="agent"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
    )
    op.create_index("ix_users_org_id_id", "users", ["organization_id", "id"])

    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("phone", sa.String(40)),
        sa.Column("external_reference", sa.String(120)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_customers_org_email", "customers", ["organization_id", "email"])

    op.create_table(
        "tickets",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            sa.Uuid(),
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("assignee_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("subject", sa.String(240), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(30), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_tickets_org_status_created", "tickets", ["organization_id", "status", "created_at"]
    )
    op.create_index("ix_tickets_org_customer", "tickets", ["organization_id", "customer_id"])

    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ticket_id", sa.Uuid(), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("channel", sa.String(30), nullable=False, server_default="web"),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_conversations_org_ticket", "conversations", ["organization_id", "ticket_id"]
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sender_type", sa.String(20), nullable=False),
        sa.Column("sender_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(30), nullable=False, server_default="text"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_messages_org_conversation_created",
        "messages",
        ["organization_id", "conversation_id", "created_at"],
    )

    # Tenant isolation. Application DB role must not be a superuser or BYPASSRLS role.
    for table in ("users", "customers", "tickets", "conversations", "messages"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY tenant_isolation ON "{table}"
            USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
            WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)'''
        )


def downgrade():
    for table in ("messages", "conversations", "tickets", "customers", "users"):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
    op.drop_table("messages")
    op.drop_index("ix_conversations_org_ticket", table_name="conversations")
    op.drop_table("conversations")
    op.drop_index("ix_tickets_org_customer", table_name="tickets")
    op.drop_index("ix_tickets_org_status_created", table_name="tickets")
    op.drop_table("tickets")
    op.drop_index("ix_customers_org_email", table_name="customers")
    op.drop_table("customers")
    op.drop_index("ix_users_org_id_id", table_name="users")
    op.drop_table("users")
    op.drop_table("organizations")
