"""Add shared account identities while preserving tenant user memberships.

Revision ID: 0035_shared_auth_identities
Revises: 0034_catalog_variant_connection_integrity
"""

import sqlalchemy as sa
from alembic import context, op

revision = "0035_shared_auth_identities"
down_revision = "0034_catalog_variant_connection_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    duplicate_check = """SELECT count(*) FROM (
                 SELECT organization_id, lower(trim(email)) AS email
                 FROM users GROUP BY organization_id, lower(trim(email)) HAVING count(*) > 1
               ) AS duplicate_groups"""
    if context.is_offline_mode():
        op.execute(
            """DO $$ BEGIN
              IF EXISTS (
                SELECT 1 FROM users
                GROUP BY organization_id, lower(trim(email))
                HAVING count(*) > 1
              ) THEN
                RAISE EXCEPTION 'Cannot link shared auth identities: duplicate normalized emails exist within a workspace';
              END IF;
            END $$;"""
        )
        duplicate_same_tenant = 0
    else:
        duplicate_same_tenant = connection.execute(sa.text(duplicate_check)).scalar_one()
    if duplicate_same_tenant:
        raise RuntimeError(
            "Cannot link shared auth identities: multiple membership rows in the same "
            "workspace use the same normalized email. Reconcile those rows before retrying."
        )

    op.create_table(
        "auth_identities",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("email_normalized", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column(
            "password_reset_required", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("email_normalized", name="uq_auth_identities_email_normalized"),
    )
    op.create_table(
        "auth_identity_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "identity_id",
            sa.Uuid(),
            sa.ForeignKey("auth_identities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_auth_identity_membership_user"),
        sa.UniqueConstraint(
            "identity_id", "organization_id", name="uq_auth_identity_membership_org"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name="fk_auth_identity_memberships_org_user",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_auth_identity_memberships_identity",
        "auth_identity_memberships",
        ["identity_id", "organization_id"],
    )
    op.create_table(
        "auth_challenges",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "identity_id",
            sa.Uuid(),
            sa.ForeignKey("auth_identities.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(24), nullable=False),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("code_digest", sa.String(64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("send_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_auth_challenges_token_hash"),
        sa.ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name="fk_auth_challenges_org_user",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "purpose IN ('login', 'registration', 'password_reset')",
            name="ck_auth_challenges_purpose",
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 5", name="ck_auth_challenges_attempt_count"
        ),
        sa.CheckConstraint("send_count BETWEEN 0 AND 3", name="ck_auth_challenges_send_count"),
    )
    op.create_index(
        "ix_auth_challenges_identity_purpose_created",
        "auth_challenges",
        ["identity_id", "purpose", "created_at"],
    )

    op.execute(
        """INSERT INTO auth_identities
          (id, email_normalized, password_hash, password_reset_required)
        SELECT gen_random_uuid(), normalized_email,
          CASE WHEN count(*) > 1 THEN NULL ELSE (array_agg(password_hash ORDER BY created_at, id))[1] END,
          count(*) > 1
        FROM (
          SELECT id, created_at, password_hash, lower(trim(email)) AS normalized_email
          FROM users
        ) AS normalized_users
        GROUP BY normalized_email"""
    )
    op.execute(
        """INSERT INTO auth_identity_memberships
          (id, identity_id, organization_id, user_id)
        SELECT gen_random_uuid(), identities.id, users.organization_id, users.id
        FROM users
        JOIN auth_identities AS identities
          ON identities.email_normalized = lower(trim(users.email))"""
    )

    # Membership-directory reads are available only after a valid identity has
    # been placed in transaction-local auth context. Tenant writes also require
    # the matching tenant context.
    op.execute("ALTER TABLE auth_identity_memberships ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE auth_identity_memberships FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY auth_identity_membership_scope ON auth_identity_memberships
        USING (
          identity_id = NULLIF(current_setting('app.current_identity', true), '')::uuid
          OR organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
        )
        WITH CHECK (
          identity_id = NULLIF(current_setting('app.current_identity', true), '')::uuid
          AND organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
        )"""
    )
    op.execute("ALTER TABLE auth_identities ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE auth_identities FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY auth_identity_scope ON auth_identities
        USING (
          email_normalized = NULLIF(current_setting('app.auth_email', true), '')
          OR id = NULLIF(current_setting('app.current_identity', true), '')::uuid
        )
        WITH CHECK (
          email_normalized = NULLIF(current_setting('app.auth_email', true), '')
          OR id = NULLIF(current_setting('app.current_identity', true), '')::uuid
        )"""
    )
    op.execute("ALTER TABLE auth_challenges ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE auth_challenges FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY auth_challenge_token_scope ON auth_challenges
        USING (
          token_hash = NULLIF(current_setting('app.auth_challenge', true), '')
        )
        WITH CHECK (
          token_hash = NULLIF(current_setting('app.auth_challenge', true), '')
        )"""
    )
    op.execute(
        """CREATE POLICY users_identity_lookup ON users FOR SELECT
        USING (
          id IN (
            SELECT user_id FROM auth_identity_memberships
            WHERE identity_id = NULLIF(current_setting('app.current_identity', true), '')::uuid
          )
        )"""
    )
    op.execute(
        """CREATE POLICY organizations_identity_lookup ON organizations FOR SELECT
        USING (
          id IN (
            SELECT organization_id FROM auth_identity_memberships
            WHERE identity_id = NULLIF(current_setting('app.current_identity', true), '')::uuid
          )
        )"""
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS organizations_identity_lookup ON organizations")
    op.execute("DROP POLICY IF EXISTS users_identity_lookup ON users")
    op.execute("DROP POLICY IF EXISTS auth_challenge_token_scope ON auth_challenges")
    op.execute("DROP POLICY IF EXISTS auth_identity_scope ON auth_identities")
    op.execute("DROP POLICY IF EXISTS auth_identity_membership_scope ON auth_identity_memberships")
    op.drop_index("ix_auth_challenges_identity_purpose_created", table_name="auth_challenges")
    op.drop_table("auth_challenges")
    op.drop_index("ix_auth_identity_memberships_identity", table_name="auth_identity_memberships")
    op.drop_table("auth_identity_memberships")
    op.drop_table("auth_identities")
