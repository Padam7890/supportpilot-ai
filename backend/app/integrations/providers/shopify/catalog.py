"""Shopify GraphQL product catalog adapter and provider response normalization."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from html.parser import HTMLParser
from typing import Any

from pydantic import ValidationError

from app.integrations.core.contracts.catalog import (
    CatalogImage,
    CatalogPriceSnapshot,
    CatalogProductPage,
    CatalogProductSnapshot,
    CatalogVariantSnapshot,
)
from app.integrations.core.contracts.provider import IntegrationConnectionRef
from app.integrations.providers.shopify.client import ShopifyAPIError, graphql

PRODUCTS_QUERY = """
query SupportPilotProducts($first: Int!, $after: String, $query: String) {
  products(first: $first, after: $after, query: $query, sortKey: UPDATED_AT) {
    nodes {
      id title descriptionHtml vendor productType handle onlineStoreUrl status updatedAt
      featuredImage { url altText }
      images(first: 20) { nodes { url altText } }
      variants(first: 25) {
        nodes {
          id title sku price { amount currencyCode } compareAtPrice { amount currencyCode }
          availableForSale selectedOptions { name value } updatedAt
        }
        pageInfo { hasNextPage endCursor }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

PRODUCT_VARIANTS_QUERY = """
query SupportPilotProductVariants($id: ID!, $first: Int!, $after: String) {
  product(id: $id) {
    variants(first: $first, after: $after) {
      nodes {
        id title sku price { amount currencyCode } compareAtPrice { amount currencyCode }
        availableForSale selectedOptions { name value } updatedAt
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

PRODUCT_BY_ID_QUERY = """
query SupportPilotProduct($id: ID!) {
  product(id: $id) {
    id title descriptionHtml vendor productType handle onlineStoreUrl status updatedAt
    featuredImage { url altText }
    images(first: 20) { nodes { url altText } }
    variants(first: 25) {
      nodes {
        id title sku price { amount currencyCode } compareAtPrice { amount currencyCode }
        availableForSale selectedOptions { name value } updatedAt
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

VARIANT_BY_ID_QUERY = """
query SupportPilotVariant($id: ID!) {
  productVariant(id: $id) {
    id title sku price { amount currencyCode } compareAtPrice { amount currencyCode }
    availableForSale selectedOptions { name value } updatedAt
  }
}
"""

MAX_PRODUCTS_PER_PAGE = 20
MAX_VARIANTS_PER_PAGE = 250
MAX_VARIANT_PAGES_PER_PRODUCT = 8


class _PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def plain_text(value: str | None) -> str | None:
    if not value:
        return None
    parser = _PlainText()
    parser.feed(value)
    text = " ".join(" ".join(parser.parts).split())
    return text[:20000] or None


def _gid(value: Any, resource: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ShopifyAPIError("shopify_invalid_product_response")
    cleaned = value.strip()
    if cleaned.startswith("gid://shopify/"):
        return cleaned
    if cleaned.isdigit():
        return f"gid://shopify/{resource}/{cleaned}"
    raise ShopifyAPIError("shopify_invalid_product_response")


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def map_variant(node: dict[str, Any]) -> CatalogVariantSnapshot:
    price = node.get("price")
    if not isinstance(price, dict):
        raise ShopifyAPIError("shopify_invalid_product_response")
    amount = price.get("amount")
    currency = price.get("currencyCode")
    if not isinstance(amount, str) or not isinstance(currency, str):
        raise ShopifyAPIError("shopify_invalid_product_response")
    compare = node.get("compareAtPrice")
    compare_amount = compare.get("amount") if isinstance(compare, dict) else None
    selected = node.get("selectedOptions")
    attributes: dict[str, str] = {}
    if isinstance(selected, list):
        for option in selected:
            if isinstance(option, dict) and isinstance(option.get("name"), str) and isinstance(option.get("value"), str):
                attributes[option["name"][:100]] = option["value"][:255]
    available = node.get("availableForSale")
    return CatalogVariantSnapshot(
        external_variant_id=_gid(node.get("id"), "ProductVariant"),
        title=str(node.get("title") or "Default")[:255],
        sku=str(node["sku"])[:255] if isinstance(node.get("sku"), str) else None,
        attributes=attributes,
        price=str(amount),
        compare_at_price=str(compare_amount) if compare_amount is not None else None,
        currency=currency.upper(),
        availability="available" if available is True else "unavailable" if available is False else "unknown",
        provider_updated_at=_parse_time(node.get("updatedAt")),
    )


def map_product(node: dict[str, Any]) -> CatalogProductSnapshot:
    image_nodes: list[dict[str, Any]] = []
    images = node.get("images")
    if isinstance(images, dict) and isinstance(images.get("nodes"), list):
        image_nodes.extend(item for item in images["nodes"] if isinstance(item, dict))
    featured = node.get("featuredImage")
    if isinstance(featured, dict) and featured not in image_nodes:
        image_nodes.insert(0, featured)
    normalized_images: list[CatalogImage] = []
    seen_urls: set[str] = set()
    for image in image_nodes[:20]:
        image_url = image.get("url")
        if not isinstance(image_url, str) or not image_url.startswith("https://") or image_url in seen_urls:
            continue
        seen_urls.add(image_url)
        normalized_images.append(
            CatalogImage(url=image_url, alt_text=image.get("altText")[:500] if isinstance(image.get("altText"), str) else None)
        )
    variant_connection = node.get("variants")
    variant_nodes = variant_connection.get("nodes", []) if isinstance(variant_connection, dict) else []
    if not isinstance(variant_nodes, list):
        raise ShopifyAPIError("shopify_invalid_product_response")
    status_map = {"ACTIVE": "active", "DRAFT": "draft", "ARCHIVED": "archived"}
    canonical_url = node.get("onlineStoreUrl")
    return CatalogProductSnapshot(
        external_product_id=_gid(node.get("id"), "Product"),
        title=str(node.get("title") or "Untitled product")[:500],
        description=plain_text(node.get("descriptionHtml")),
        brand=str(node["vendor"])[:255] if isinstance(node.get("vendor"), str) and node["vendor"] else None,
        category=str(node["productType"])[:255] if isinstance(node.get("productType"), str) and node["productType"] else None,
        images=normalized_images,
        canonical_url=canonical_url if isinstance(canonical_url, str) and canonical_url.startswith("https://") else None,
        status=status_map.get(str(node.get("status", "")).upper(), "unknown"),
        variants=[map_variant(item) for item in variant_nodes if isinstance(item, dict)],
        provider_updated_at=_parse_time(node.get("updatedAt")),
    )


def _safe_map_product(node: dict[str, Any]) -> CatalogProductSnapshot:
    try:
        return map_product(node)
    except (ValidationError, TypeError, ValueError) as exc:
        raise ShopifyAPIError("shopify_invalid_product_response") from exc


def _safe_map_variant(node: dict[str, Any]) -> CatalogVariantSnapshot:
    try:
        return map_variant(node)
    except (ValidationError, TypeError, ValueError) as exc:
        raise ShopifyAPIError("shopify_invalid_product_response") from exc


CredentialResolver = Callable[[IntegrationConnectionRef], Awaitable[tuple[str, str]]]


class ShopifyProductCatalogAdapter:
    """Shopify catalog capability; token resolution is injected and request scoped."""

    def __init__(self, resolve_credentials: CredentialResolver):
        self._resolve_credentials = resolve_credentials

    async def _auth(self, connection: IntegrationConnectionRef) -> tuple[str, str]:
        if connection.provider_id != "shopify":
            raise ValueError("Shopify catalog adapter received a different provider")
        return await self._resolve_credentials(connection)

    async def list_products(
        self,
        connection: IntegrationConnectionRef,
        *,
        limit: int,
        cursor: str | None,
        updated_after: datetime | None = None,
    ) -> CatalogProductPage:
        if not 1 <= limit <= MAX_PRODUCTS_PER_PAGE:
            raise ValueError(f"Product page limit must be between 1 and {MAX_PRODUCTS_PER_PAGE}")
        shop, token = await self._auth(connection)
        search = f"updated_at:>{updated_after.isoformat()}" if updated_after else None
        data = await graphql(shop, token, PRODUCTS_QUERY, {"first": limit, "after": cursor, "query": search})
        products = data.get("products")
        if not isinstance(products, dict) or not isinstance(products.get("nodes"), list) or not isinstance(products.get("pageInfo"), dict):
            raise ShopifyAPIError("shopify_invalid_product_response")
        items = [await self._complete_product_variants(shop, token, item) for item in products["nodes"] if isinstance(item, dict)]
        page = products["pageInfo"]
        has_more = page.get("hasNextPage") is True
        next_cursor = page.get("endCursor") if has_more else None
        if has_more and not isinstance(next_cursor, str):
            raise ShopifyAPIError("shopify_invalid_product_response")
        return CatalogProductPage(items=items, next_cursor=next_cursor, has_more=has_more)

    async def _complete_product_variants(self, shop: str, token: str, node: dict[str, Any]) -> CatalogProductSnapshot:
        mapped = _safe_map_product(node)
        variants_page = node.get("variants")
        page_info = variants_page.get("pageInfo") if isinstance(variants_page, dict) else None
        if not isinstance(page_info, dict):
            raise ShopifyAPIError("shopify_invalid_product_response")
        has_more = page_info.get("hasNextPage") is True
        cursor = page_info.get("endCursor")
        if has_more and not isinstance(cursor, str):
            raise ShopifyAPIError("shopify_invalid_product_response")
        variants = list(mapped.variants)
        product_id = _gid(node.get("id"), "Product")
        page_count = 0
        while has_more:
            page_count += 1
            if page_count > MAX_VARIANT_PAGES_PER_PRODUCT:
                raise ShopifyAPIError("shopify_product_variant_limit_exceeded", status_code=422)
            response = await graphql(
                shop,
                token,
                PRODUCT_VARIANTS_QUERY,
                {"id": product_id, "first": MAX_VARIANTS_PER_PAGE, "after": cursor},
            )
            product = response.get("product")
            connection_data = product.get("variants") if isinstance(product, dict) else None
            if not isinstance(connection_data, dict) or not isinstance(connection_data.get("nodes"), list) or not isinstance(connection_data.get("pageInfo"), dict):
                raise ShopifyAPIError("shopify_invalid_product_response")
            variants.extend(_safe_map_variant(item) for item in connection_data["nodes"] if isinstance(item, dict))
            has_more = connection_data["pageInfo"].get("hasNextPage") is True
            cursor = connection_data["pageInfo"].get("endCursor") if has_more else None
            if has_more and not isinstance(cursor, str):
                raise ShopifyAPIError("shopify_invalid_product_response")
        return mapped.model_copy(update={"variants": variants})

    async def get_product(self, connection: IntegrationConnectionRef, *, external_product_id: str) -> CatalogProductSnapshot | None:
        shop, token = await self._auth(connection)
        data = await graphql(shop, token, PRODUCT_BY_ID_QUERY, {"id": _gid(external_product_id, "Product")})
        node = data.get("product")
        if node is None:
            return None
        if not isinstance(node, dict):
            raise ShopifyAPIError("shopify_invalid_product_response")
        return await self._complete_product_variants(shop, token, node)

    async def get_variant(self, connection: IntegrationConnectionRef, *, external_variant_id: str) -> CatalogVariantSnapshot | None:
        shop, token = await self._auth(connection)
        data = await graphql(shop, token, VARIANT_BY_ID_QUERY, {"id": _gid(external_variant_id, "ProductVariant")})
        node = data.get("productVariant")
        if node is None:
            return None
        if not isinstance(node, dict):
            raise ShopifyAPIError("shopify_invalid_product_response")
        return _safe_map_variant(node)

    async def get_current_price(
        self,
        connection: IntegrationConnectionRef,
        *,
        external_variant_id: str,
    ) -> CatalogPriceSnapshot | None:
        variant = await self.get_variant(connection, external_variant_id=external_variant_id)
        if variant is None:
            return None
        return CatalogPriceSnapshot(
            price=variant.price,
            compare_at_price=variant.compare_at_price,
            currency=variant.currency,
            provider_updated_at=variant.provider_updated_at,
        )

    async def search_products(self, connection: IntegrationConnectionRef, *, query: str, limit: int, cursor: str | None = None) -> CatalogProductPage:
        normalized = " ".join(query.split())[:120]
        if not normalized:
            return await self.list_products(connection, limit=limit, cursor=cursor)
        safe_query = 'title:"' + normalized.replace("\\", "\\\\").replace('"', '\\"') + '"'
        if not 1 <= limit <= MAX_PRODUCTS_PER_PAGE:
            raise ValueError(f"Product page limit must be between 1 and {MAX_PRODUCTS_PER_PAGE}")
        shop, token = await self._auth(connection)
        data = await graphql(shop, token, PRODUCTS_QUERY, {"first": limit, "after": cursor, "query": safe_query})
        products = data.get("products")
        if not isinstance(products, dict) or not isinstance(products.get("nodes"), list) or not isinstance(products.get("pageInfo"), dict):
            raise ShopifyAPIError("shopify_invalid_product_response")
        items = [await self._complete_product_variants(shop, token, item) for item in products["nodes"] if isinstance(item, dict)]
        page = products["pageInfo"]
        has_more = page.get("hasNextPage") is True
        next_cursor = page.get("endCursor") if has_more else None
        if has_more and not isinstance(next_cursor, str):
            raise ShopifyAPIError("shopify_invalid_product_response")
        return CatalogProductPage(items=items, next_cursor=next_cursor, has_more=has_more)
