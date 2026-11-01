"""Persist structured recommendation results on durable AI executions."""

import sqlalchemy as sa
from alembic import op

revision = "0026_ai_recommendations"
down_revision = "0025_commerce_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_executions", sa.Column("recommendation_result", sa.JSON(), nullable=True))
    op.drop_constraint("ck_ai_executions_kind", "ai_executions", type_="check")
    op.create_check_constraint(
        "ck_ai_executions_kind",
        "ai_executions",
        "kind IN ('playground', 'reply_draft', 'widget_reply', 'recommendation')",
    )
    op.create_index(
        "ix_catalog_products_recommendation_search",
        "catalog_products",
        [sa.text(
            "to_tsvector('simple'::regconfig, coalesce(title, '') || ' ' || "
            "coalesce(description, '') || ' ' || coalesce(brand, '') || ' ' || "
            "coalesce(category, '') || ' ' || coalesce(specifications::text, ''))"
        )],
        postgresql_using="gin",
    )


def downgrade() -> None:
    recommendation_count = op.get_bind().execute(
        sa.text("SELECT count(*) FROM ai_executions WHERE kind = 'recommendation'")
    ).scalar_one()
    if recommendation_count:
        raise RuntimeError(
            "Cannot downgrade recommendation support while recommendation executions exist; preserve or export them first."
        )
    op.drop_index("ix_catalog_products_recommendation_search", table_name="catalog_products")
    op.drop_constraint("ck_ai_executions_kind", "ai_executions", type_="check")
    op.create_check_constraint(
        "ck_ai_executions_kind",
        "ai_executions",
        "kind IN ('playground', 'reply_draft', 'widget_reply')",
    )
    op.drop_column("ai_executions", "recommendation_result")
