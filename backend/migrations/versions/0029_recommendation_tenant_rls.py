"""Align recommendation-table RLS policies with runtime verification."""

from alembic import op

revision = "0029_recommendation_tenant_rls"
down_revision = "0028_recommendation_settings_analytics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER POLICY recommendation_settings_tenant_policy ON recommendation_settings "
        "RENAME TO tenant_isolation"
    )
    op.execute(
        "ALTER POLICY recommendation_events_tenant_policy ON recommendation_events "
        "RENAME TO tenant_isolation"
    )


def downgrade() -> None:
    op.execute(
        "ALTER POLICY tenant_isolation ON recommendation_events "
        "RENAME TO recommendation_events_tenant_policy"
    )
    op.execute(
        "ALTER POLICY tenant_isolation ON recommendation_settings "
        "RENAME TO recommendation_settings_tenant_policy"
    )
