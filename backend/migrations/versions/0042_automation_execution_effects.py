"""Durable idempotency keys for automation side effects."""

import sqlalchemy as sa
from alembic import op

revision = "0042_automation_execution_effects"
down_revision = "0041_automation_canvas_layout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automation_execution_effects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("effect_key", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(trim(effect_key)) > 0", name="ck_automation_execution_effects_key_nonblank"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_automation_execution_effects_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "execution_id"],
            ["automation_executions.organization_id", "automation_executions.id"],
            name="fk_automation_execution_effects_org_execution",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_automation_execution_effects"),
        sa.UniqueConstraint(
            "organization_id",
            "execution_id",
            "effect_key",
            name="uq_automation_execution_effects_org_exec_key",
        ),
    )
    op.create_index(
        "ix_automation_execution_effects_org_exec",
        "automation_execution_effects",
        ["organization_id", "execution_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_automation_execution_effects_org_exec", table_name="automation_execution_effects")
    op.drop_table("automation_execution_effects")
