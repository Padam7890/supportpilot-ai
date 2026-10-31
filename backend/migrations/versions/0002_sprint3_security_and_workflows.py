"""Add tenant-safe relationships, auth sessions, invitations, and activity."""

import sqlalchemy as sa
from alembic import op

revision = "0002_sprint3"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM tickets t JOIN customers c ON c.id = t.customer_id
            WHERE t.organization_id <> c.organization_id
          ) THEN RAISE EXCEPTION 'Sprint 3 migration stopped: cross-organization ticket/customer reference'; END IF;
          IF EXISTS (
            SELECT 1 FROM tickets t JOIN users u ON u.id = t.assignee_id
            WHERE t.assignee_id IS NOT NULL AND t.organization_id <> u.organization_id
          ) THEN RAISE EXCEPTION 'Sprint 3 migration stopped: cross-organization ticket assignee'; END IF;
          IF EXISTS (
            SELECT 1 FROM conversations c JOIN tickets t ON t.id = c.ticket_id
            WHERE c.organization_id <> t.organization_id
          ) THEN RAISE EXCEPTION 'Sprint 3 migration stopped: cross-organization conversation/ticket reference'; END IF;
          IF EXISTS (
            SELECT 1 FROM messages m JOIN conversations c ON c.id = m.conversation_id
            WHERE m.organization_id <> c.organization_id
          ) THEN RAISE EXCEPTION 'Sprint 3 migration stopped: cross-organization message/conversation reference'; END IF;
          IF EXISTS (
            SELECT 1 FROM messages m JOIN users u ON u.id = m.sender_user_id
            WHERE m.sender_user_id IS NOT NULL AND m.organization_id <> u.organization_id
          ) THEN RAISE EXCEPTION 'Sprint 3 migration stopped: cross-organization message sender'; END IF;
        END $$;
        """
    )

    for table, constraint in (
        ("users", "uq_users_org_id"),
        ("customers", "uq_customers_org_id"),
        ("tickets", "uq_tickets_org_id"),
        ("conversations", "uq_conversations_org_id"),
        ("messages", "uq_messages_org_id"),
    ):
        op.create_unique_constraint(constraint, table, ["organization_id", "id"])

    for table, constraint, local_cols, referred_table, referred_cols, action in (
        (
            "tickets",
            "fk_tickets_org_customer",
            ["organization_id", "customer_id"],
            "customers",
            ["organization_id", "id"],
            "RESTRICT",
        ),
        (
            "tickets",
            "fk_tickets_org_assignee",
            ["organization_id", "assignee_id"],
            "users",
            ["organization_id", "id"],
            "RESTRICT",
        ),
        (
            "conversations",
            "fk_conversations_org_ticket",
            ["organization_id", "ticket_id"],
            "tickets",
            ["organization_id", "id"],
            "CASCADE",
        ),
        (
            "messages",
            "fk_messages_org_conversation",
            ["organization_id", "conversation_id"],
            "conversations",
            ["organization_id", "id"],
            "CASCADE",
        ),
        (
            "messages",
            "fk_messages_org_sender",
            ["organization_id", "sender_user_id"],
            "users",
            ["organization_id", "id"],
            "RESTRICT",
        ),
    ):
        op.drop_constraint(
            {
                "fk_tickets_org_customer": "tickets_customer_id_fkey",
                "fk_tickets_org_assignee": "tickets_assignee_id_fkey",
                "fk_conversations_org_ticket": "conversations_ticket_id_fkey",
                "fk_messages_org_conversation": "messages_conversation_id_fkey",
                "fk_messages_org_sender": "messages_sender_user_id_fkey",
            }[constraint],
            table,
            type_="foreignkey",
        )
        op.create_foreign_key(
            constraint, table, referred_table, local_cols, referred_cols, ondelete=action
        )

    op.create_table(
        "refresh_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name="fk_refresh_sessions_org_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_refresh_sessions_org_id"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_sessions_token_hash"),
    )
    op.create_table(
        "team_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("invited_by_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "invited_by_id"],
            ["users.organization_id", "users.id"],
            name="fk_team_invitations_org_inviter",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_team_invitations_org_id"),
        sa.UniqueConstraint("token_hash", name="uq_team_invitations_token_hash"),
    )
    op.create_table(
        "ticket_activities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid()),
        sa.Column("activity_type", sa.String(40), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "ticket_id"],
            ["tickets.organization_id", "tickets.id"],
            name="fk_ticket_activities_org_ticket",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_ticket_activities_org_actor",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ticket_activities_org_ticket_created",
        "ticket_activities",
        ["organization_id", "ticket_id", "created_at"],
    )
    for table in ("refresh_sessions", "team_invitations", "ticket_activities"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY tenant_isolation ON "{table}"
            USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
            WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)'''
        )


def downgrade() -> None:
    for table in ("ticket_activities", "team_invitations", "refresh_sessions"):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
    op.drop_index("ix_ticket_activities_org_ticket_created", table_name="ticket_activities")
    op.drop_table("ticket_activities")
    op.drop_table("team_invitations")
    op.drop_table("refresh_sessions")
    for table, name in (
        ("messages", "fk_messages_org_sender"),
        ("messages", "fk_messages_org_conversation"),
        ("conversations", "fk_conversations_org_ticket"),
        ("tickets", "fk_tickets_org_assignee"),
        ("tickets", "fk_tickets_org_customer"),
    ):
        op.drop_constraint(name, table, type_="foreignkey")
    op.create_foreign_key(
        "messages_sender_user_id_fkey",
        "messages",
        "users",
        ["sender_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "messages_conversation_id_fkey",
        "messages",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "conversations_ticket_id_fkey",
        "conversations",
        "tickets",
        ["ticket_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "tickets_assignee_id_fkey", "tickets", "users", ["assignee_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "tickets_customer_id_fkey",
        "tickets",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    for table, constraint in (
        ("conversations", "uq_conversations_org_id"),
        ("tickets", "uq_tickets_org_id"),
        ("customers", "uq_customers_org_id"),
        ("users", "uq_users_org_id"),
        ("messages", "uq_messages_org_id"),
    ):
        op.drop_constraint(constraint, table, type_="unique")
