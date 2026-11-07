"""Add configurable first-response SLA targets to each workspace."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0058_first_response_sla_policy"
down_revision = "0057_tenant_teams"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "first_response_sla_minutes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text(
                '\'{"low"\\:1440,"normal"\\:480,"high"\\:120,"urgent"\\:30}\'::jsonb'
            ),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "first_response_sla_minutes")
