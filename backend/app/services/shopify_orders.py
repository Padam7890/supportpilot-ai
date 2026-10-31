"""Authorization-safe Shopify order lookup primitives.

Callers must resolve the installation from the authenticated user's organization
and pass a trusted customer email from the linked customer/ticket context. The
customer email must not come from an untrusted model-generated argument.
"""

from typing import Any

from app.services.shopify_client import fetch_orders


def _quoted_search_value(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def find_exact_order(nodes: list[dict[str, Any]], order_number: str, customer_email: str) -> dict[str, Any] | None:
    expected_number = order_number.strip().lstrip("#").casefold()
    expected_email = customer_email.strip().casefold()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        customer = node.get("customer")
        if not isinstance(customer, dict):
            continue
        actual_email = customer.get("email")
        actual_number = str(node.get("name", "")).strip().lstrip("#").casefold()
        if (
            actual_number == expected_number
            and isinstance(actual_email, str)
            and actual_email.strip().casefold() == expected_email
        ):
            return node
    return None


async def lookup_authorized_order(
    *,
    shop_domain: str,
    access_token: str,
    order_number: str,
    customer_email: str,
) -> dict[str, Any] | None:
    """Return an order only when Shopify confirms both identity values.

    Reusable by HTTP handlers and future agent tools. The caller is responsible
    for tenant-scoping the Shopify installation and supplying the customer email
    from an authorized SupportPilot record.
    """
    normalized_number = order_number.strip()
    if not normalized_number.startswith("#"):
        normalized_number = f"#{normalized_number}"
    normalized_email = customer_email.strip().casefold()
    search = (
        f"name:{_quoted_search_value(normalized_number)} AND "
        f"email:{_quoted_search_value(normalized_email)}"
    )
    page = await fetch_orders(
        shop_domain,
        access_token,
        search_query=search,
        limit=5,
        cursor=None,
    )
    return find_exact_order(page["nodes"], normalized_number, normalized_email)
