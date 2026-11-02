"""Translate Shopify provider failures into stable SupportPilot API errors."""

from fastapi import HTTPException

from app.integrations.providers.shopify.client import ShopifyAPIError


def to_api_error(exc: ShopifyAPIError) -> HTTPException:
    """Map provider error codes to the existing public HTTP status and detail contract."""
    if exc.reason_code == "shop_not_permitted":
        return HTTPException(
            status_code=403,
            detail=(
                "Shopify does not allow these app credentials to access this store. "
                "The app and store must belong to the same Shopify organization. "
                "Check that both appear under the same organization in Shopify Dev Dashboard."
            ),
        )
    if exc.reason_code in {"invalid_client", "invalid_client_id", "invalid_client_secret"}:
        return HTTPException(
            status_code=403,
            detail="Shopify rejected the app credentials. Verify the Client ID and Client Secret in Shopify Dev Dashboard.",
        )
    messages = {
        "shopify_unavailable": "Shopify is temporarily unavailable. Try again shortly.",
        "shopify_authorization_failed": "Shopify authorization could not be completed.",
        "shopify_scope_or_data_access_required": (
            "Shopify denied this order-data request. Check that the connected app has effective order-read access "
            "(write_orders includes read access), the store has granted the current app permissions, and the order "
            "is within the accessible order-history window."
        ),
        "shopify_access_denied": (
            "Shopify denied this request. Review the Shopify API diagnostic event for its access-denied code and field path."
        ),
        "shopify_required_scopes_missing": "The current Shopify access token is missing required app scopes.",
        "shopify_product_scope_missing": "The current Shopify access token does not include read_products.",
        "shopify_graphql_error": "Shopify returned a GraphQL validation or execution error. Review its safe diagnostic details in the API logs.",
        "shopify_rate_limited": "Shopify rate-limited this request. Retry after the provider backoff.",
        "shopify_credentials_unavailable": "Shopify credentials are unavailable. Check the server encryption configuration.",
        "shopify_reauthorization_required": "The Shopify connection needs to be reconnected.",
        "shopify_request_rejected": "Shopify rejected the read request.",
    }
    return HTTPException(
        status_code=exc.status_code,
        detail=messages.get(exc.code, "Shopify returned an invalid response."),
    )
