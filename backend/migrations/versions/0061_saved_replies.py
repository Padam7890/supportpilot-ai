"""Add tenant-scoped reusable support replies."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0061_saved_replies"
down_revision = "0060_knowledge_base_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_replies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("shortcut", sa.String(length=40), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_saved_replies_org_creator",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "updated_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_saved_replies_org_updater",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_saved_replies_org_id"),
        sa.UniqueConstraint("organization_id", "shortcut", name="uq_saved_replies_org_shortcut"),
        sa.CheckConstraint("length(trim(title)) >= 2", name="ck_saved_replies_title_nonempty"),
        sa.CheckConstraint("length(trim(body)) >= 1", name="ck_saved_replies_body_nonempty"),
    )
    op.create_index(
        "ix_saved_replies_org_active_title",
        "saved_replies",
        ["organization_id", "is_active", "title"],
    )
    op.execute('ALTER TABLE "saved_replies" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "saved_replies" FORCE ROW LEVEL SECURITY')
    op.execute(
        """CREATE POLICY tenant_isolation ON saved_replies
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"""
    )


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM saved_replies) THEN
          RAISE EXCEPTION 'Refusing to remove saved replies while workspace content exists';
        END IF;
        END $$"""
    )
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "saved_replies"')
    op.drop_index("ix_saved_replies_org_active_title", table_name="saved_replies")
    op.drop_table("saved_replies")
