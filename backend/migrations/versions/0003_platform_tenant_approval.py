"""Add isolated platform owners and tenant registration review."""

import sqlalchemy as sa
from alembic import op

revision = "0003_platform_approval"
down_revision = "0002_sprint3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_owners",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_platform_owners_email"),
    )
    op.create_table(
        "platform_refresh_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("platform_owner_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["platform_owner_id"], ["platform_owners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_platform_refresh_token_hash"),
    )

    op.add_column(
        "organizations",
        sa.Column(
            "approval_status", sa.String(length=20), nullable=False, server_default="approved"
        ),
    )
    op.add_column(
        "organizations",
        sa.Column("reviewed_by_platform_owner_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_organizations_approval_status",
        "organizations",
        "approval_status IN ('pending', 'approved', 'rejected')",
    )
    op.create_foreign_key(
        "fk_organizations_reviewed_by_platform_owner",
        "organizations",
        "platform_owners",
        ["reviewed_by_platform_owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_organizations_approval_created",
        "organizations",
        ["approval_status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_organizations_approval_created", table_name="organizations")
    op.drop_constraint(
        "fk_organizations_reviewed_by_platform_owner", "organizations", type_="foreignkey"
    )
    op.drop_constraint("ck_organizations_approval_status", "organizations", type_="check")
    op.drop_column("organizations", "reviewed_at")
    op.drop_column("organizations", "reviewed_by_platform_owner_id")
    op.drop_column("organizations", "approval_status")
    op.drop_table("platform_refresh_sessions")
    op.drop_table("platform_owners")
