"""Require catalog variants and their products to share one provider connection."""

from alembic import op

revision = "0034_catalog_variant_connection_integrity"
down_revision = "0033_message_connection_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Do not silently repair records: operators must reconcile inconsistent
    # provider ownership before this invariant can be enforced.
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (
            SELECT 1
            FROM catalog_variants AS variant
            JOIN catalog_products AS product
              ON product.organization_id = variant.organization_id
             AND product.id = variant.product_id
            WHERE product.connection_id <> variant.connection_id
        ) THEN
            RAISE EXCEPTION
                'Catalog variants reference products from a different integration connection; reconcile rows before migration';
        END IF;
        END $$"""
    )
    op.create_unique_constraint(
        "uq_catalog_products_org_id_connection",
        "catalog_products",
        ["organization_id", "id", "connection_id"],
    )
    op.create_foreign_key(
        "fk_catalog_variants_org_product_connection",
        "catalog_variants",
        "catalog_products",
        ["organization_id", "product_id", "connection_id"],
        ["organization_id", "id", "connection_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_catalog_variants_org_product_connection",
        "catalog_variants",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_catalog_products_org_id_connection",
        "catalog_products",
        type_="unique",
    )
