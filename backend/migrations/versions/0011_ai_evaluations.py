"""Add tenant-scoped AI evaluation feedback and aggregates."""

import sqlalchemy as sa
from alembic import op

revision = "0011_ai_evaluations"
down_revision = "0010_ai_shopify_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("evaluator_user_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("rating IN ('helpful', 'not_helpful')", name="ck_ai_evaluations_rating"),
        sa.CheckConstraint(
            "category IS NULL OR category IN ('accuracy', 'grounding', 'relevance', 'tone')",
            name="ck_ai_evaluations_category",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "execution_id"],
            ["ai_executions.organization_id", "ai_executions.id"],
            name="fk_ai_evaluations_org_execution",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "evaluator_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_ai_evaluations_org_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "execution_id", "evaluator_user_id",
            name="uq_ai_evaluations_execution_evaluator",
        ),
    )
    op.create_index("ix_ai_evaluations_org_created", "ai_evaluations", ["organization_id", "created_at"])
    op.execute('ALTER TABLE "ai_evaluations" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "ai_evaluations" FORCE ROW LEVEL SECURITY')
    op.execute(
        '''CREATE POLICY tenant_isolation ON "ai_evaluations"
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)'''
    )


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "ai_evaluations"')
    op.drop_table("ai_evaluations")
