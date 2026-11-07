"""Persist visual automation node positions without changing rule execution."""

import sqlalchemy as sa
from alembic import op

revision = "0041_automation_canvas_layout"
down_revision = "0040_ai_execution_agent_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("automation_workflows", sa.Column("draft_canvas_layout", sa.JSON(), nullable=True))
    op.add_column("automation_workflow_versions", sa.Column("canvas_layout", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.execute(
        """DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM automation_workflows WHERE draft_canvas_layout IS NOT NULL)
                OR EXISTS (SELECT 1 FROM automation_workflow_versions WHERE canvas_layout IS NOT NULL) THEN
                RAISE EXCEPTION 'Cannot downgrade while automation canvas layouts exist';
            END IF;
        END $$"""
    )
    op.drop_column("automation_workflow_versions", "canvas_layout")
    op.drop_column("automation_workflows", "draft_canvas_layout")
