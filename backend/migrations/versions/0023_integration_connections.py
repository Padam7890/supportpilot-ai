"""Add tenant-scoped integration connections and encrypted credentials.

The existing Shopify installation table is deliberately retained. Existing
installations and ciphertext are copied into the generic model, with an
explicit legacy key version, so the application can verify the backfill before
cutting routes or workers over.
"""

import sqlalchemy as sa
from alembic import op

revision = "0023_integration_connections"
down_revision = "0022_conversation_ai_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.String(length=48), nullable=False),
        sa.Column("external_account_id", sa.String(length=512), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("safe_configuration", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("connected_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'connected', 'disconnected', 'error', 'reauthorization_required')",
            name="ck_integration_connections_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "connected_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_integration_connections_org_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "provider_id",
            "external_account_id",
            name="uq_integration_connections_org_provider_account",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_integration_connections_org_id"),
    )
    op.create_index(
        "ix_integration_connections_org_provider_status",
        "integration_connections",
        ["organization_id", "provider_id", "status"],
    )
    op.create_index(
        "ix_integration_connections_health",
        "integration_connections",
        ["status", "last_checked_at"],
    )

    op.create_table(
        "integration_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("credential_type", sa.String(length=48), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("key_version", sa.String(length=48), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "connection_id"],
            ["integration_connections.organization_id", "integration_connections.id"],
            name="fk_integration_credentials_org_connection",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "connection_id",
            "credential_type",
            name="uq_integration_credentials_connection_type",
        ),
    )
    op.create_index(
        "ix_integration_credentials_expiry",
        "integration_credentials",
        ["organization_id", "expires_at"],
    )

    # Safe, additive copy. Never move credential bytes into log/JSON fields.
    op.execute(
        """INSERT INTO integration_connections (
            id, organization_id, provider_id, external_account_id, display_name,
            status, safe_configuration, connected_by_user_id, connected_at,
            created_at, updated_at
        )
        SELECT gen_random_uuid(), organization_id, 'shopify', shop_domain, shop_domain,
            CASE
                WHEN disconnected_at IS NOT NULL THEN 'disconnected'
                WHEN access_token_encrypted IS NULL
                    OR (auth_mode = 'oauth' AND refresh_token_encrypted IS NULL)
                    THEN 'reauthorization_required'
                ELSE 'connected'
            END,
            json_build_object('auth_mode', auth_mode, 'granted_scopes', granted_scopes),
            connected_by_user_id, connected_at, created_at, updated_at
        FROM shopify_installations"""
    )
    op.execute(
        """INSERT INTO integration_credentials (
            id, organization_id, connection_id, credential_type,
            encrypted_value, key_version, expires_at, created_at, updated_at
        )
        SELECT gen_random_uuid(), installation.organization_id, connection.id,
            'access_token', installation.access_token_encrypted, 'shopify_legacy_v1',
            installation.access_token_expires_at, installation.created_at, installation.updated_at
        FROM shopify_installations AS installation
        JOIN integration_connections AS connection
          ON connection.organization_id = installation.organization_id
         AND connection.provider_id = 'shopify'
         AND connection.external_account_id = installation.shop_domain
        WHERE installation.access_token_encrypted IS NOT NULL"""
    )
    op.execute(
        """INSERT INTO integration_credentials (
            id, organization_id, connection_id, credential_type,
            encrypted_value, key_version, expires_at, created_at, updated_at
        )
        SELECT gen_random_uuid(), installation.organization_id, connection.id,
            'refresh_token', installation.refresh_token_encrypted, 'shopify_legacy_v1',
            installation.refresh_token_expires_at, installation.created_at, installation.updated_at
        FROM shopify_installations AS installation
        JOIN integration_connections AS connection
          ON connection.organization_id = installation.organization_id
         AND connection.provider_id = 'shopify'
         AND connection.external_account_id = installation.shop_domain
        WHERE installation.refresh_token_encrypted IS NOT NULL"""
    )

    tenant_predicate = "organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    for table in ("integration_connections", "integration_credentials"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY tenant_isolation ON "{table}"
            USING ({tenant_predicate})
            WITH CHECK ({tenant_predicate})'''
        )


def downgrade() -> None:
    # The source Shopify tables were not modified, so their records/ciphertext
    # remain intact if this additive migration is rolled back.
    for table in ("integration_credentials", "integration_connections"):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
    op.drop_index("ix_integration_credentials_expiry", table_name="integration_credentials")
    op.drop_table("integration_credentials")
    op.drop_index("ix_integration_connections_health", table_name="integration_connections")
    op.drop_index(
        "ix_integration_connections_org_provider_status",
        table_name="integration_connections",
    )
    op.drop_table("integration_connections")
