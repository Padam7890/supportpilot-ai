"""Add private tenant-scoped conversation file attachments."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0062_conversation_attachments"
down_revision = "0061_saved_replies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=80), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "conversation_id"],
            ["conversations.organization_id", "conversations.id"],
            name="fk_conversation_attachments_org_conversation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "uploaded_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_conversation_attachments_org_uploader",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("size_bytes BETWEEN 1 AND 10485760", name="ck_conversation_attachments_size"),
        sa.CheckConstraint(
            "content_type IN ('image/png', 'image/jpeg', 'image/webp', 'application/pdf', 'text/plain', 'text/markdown')",
            name="ck_conversation_attachments_type",
        ),
        sa.CheckConstraint("length(content) = size_bytes", name="ck_conversation_attachments_content_size"),
    )
    op.create_index(
        "ix_conversation_attachments_org_conversation_created",
        "conversation_attachments",
        ["organization_id", "conversation_id", "created_at", "id"],
    )
    op.execute('ALTER TABLE "conversation_attachments" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "conversation_attachments" FORCE ROW LEVEL SECURITY')
    op.execute(
        """CREATE POLICY tenant_isolation ON conversation_attachments
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"""
    )


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM conversation_attachments) THEN
          RAISE EXCEPTION 'Refusing to remove conversation attachment records and file contents';
        END IF;
        END $$"""
    )
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "conversation_attachments"')
    op.drop_index("ix_conversation_attachments_org_conversation_created", table_name="conversation_attachments")
    op.drop_table("conversation_attachments")
