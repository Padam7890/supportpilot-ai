def test_legacy_shopify_imports_reexport_provider_implementations():
    from app.integrations.connections import service as connection_service
    from app.integrations.providers.shopify import actions, client, orders, security
    from app.services import (
        integration_connections,
        shopify_actions,
        shopify_client,
        shopify_orders,
        shopify_security,
    )
    from app.services.shopify_client import graphql as imported_compatibility_graphql

    assert shopify_client.graphql is client.graphql
    assert imported_compatibility_graphql is client.graphql
    assert shopify_orders.lookup_authorized_order is orders.lookup_authorized_order
    assert shopify_security.decrypt_credential is security.decrypt_credential
    assert shopify_actions.cancel_shopify_order is actions.cancel_shopify_order
    assert (
        integration_connections.sync_shopify_connection
        is connection_service.sync_shopify_connection
    )
