"""Read-only GraphQL Admin API client for Shopify stores."""

import hashlib
import json
import logging
import re
import time
from collections.abc import Mapping
from typing import Any

import httpx

from app.core.config import settings

__all__ = [
    "CURRENT_APP_SCOPES_QUERY",
    "ORDERS_QUERY",
    "ORDER_PAGE_QUERY",
    "ShopifyAPIError",
    "effective_shopify_scopes",
    "fetch_current_app_scopes",
    "fetch_order_page",
    "fetch_orders",
    "graphql",
    "httpx",
    "log_shopify_api_event",
    "log_shopify_event",
    "parse_scope_list",
    "request_client_credentials_token",
    "request_oauth_token",
    "resolve_token_scopes",
]

logger = logging.getLogger(__name__)
_SENSITIVE_LOG_KEY_PARTS = ("secret", "token", "authorization", "assertion", "password", "hmac")
_SENSITIVE_LOG_KEYS = {"code", "state"}
_EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d .()-]{7,}\d)(?!\w)")
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+\S+")
_SHOPIFY_TOKEN_PATTERN = re.compile(r"\bshp(?:at|ss|ca|pa)_[A-Za-z0-9_-]+\b")


def _is_sensitive_log_key(key: str) -> bool:
    normalized = key.casefold()
    return normalized in _SENSITIVE_LOG_KEYS or any(part in normalized for part in _SENSITIVE_LOG_KEY_PARTS)


def _redact_for_log(value: Any, *, key: str = "", sensitive_values: tuple[str, ...] = ()) -> Any:
    """Redact credentials recursively before writing provider payloads to logs."""
    if _is_sensitive_log_key(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(child_key): _redact_for_log(child, key=str(child_key), sensitive_values=sensitive_values)
            for child_key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_for_log(child, sensitive_values=sensitive_values) for child in value]
    if isinstance(value, str):
        for secret in sensitive_values:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return f"[UNSERIALIZABLE:{type(value).__name__}]"


def log_shopify_event(event: str, **fields: Any) -> None:
    logger.info("shopify_oauth %s", json.dumps({"event": event, **_redact_for_log(fields)}, sort_keys=True))


def log_shopify_api_event(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    """Log provider diagnostics without request variables or response bodies."""
    logger.log(level, "shopify_api %s", json.dumps({"event": event, **_redact_for_log(fields)}, sort_keys=True))


class ShopifyAPIError(Exception):
    def __init__(
        self,
        code: str,
        *,
        status_code: int = 502,
        reason_code: str | None = None,
        diagnostics: tuple[dict[str, Any], ...] = (),
    ):
        self.code = code
        self.status_code = status_code
        self.reason_code = reason_code
        self.diagnostics = diagnostics
        super().__init__(code)


def _safe_graphql_diagnostics(
    errors: Any,
    *,
    sensitive_values: tuple[str, ...] = (),
    include_messages: bool = False,
) -> tuple[dict[str, Any], ...]:
    """Keep useful provider error context while redacting possible PII/secrets."""
    if not isinstance(errors, list):
        return ()
    diagnostics: list[dict[str, Any]] = []
    for error in errors[:5]:
        if not isinstance(error, dict):
            continue
        extensions = error.get("extensions")
        code = extensions.get("code") if isinstance(extensions, dict) else None
        path = error.get("path")
        safe_path = [part for part in path[:8] if isinstance(part, (str, int))] if isinstance(path, list) else None
        message = error.get("message")
        safe_message = None
        if include_messages and isinstance(message, str):
            safe_message = " ".join(message.split())[:500]
            for sensitive_value in sensitive_values:
                if sensitive_value:
                    safe_message = safe_message.replace(sensitive_value, "[REDACTED_SECRET]")
            safe_message = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", safe_message)
            safe_message = _PHONE_PATTERN.sub("[REDACTED_PHONE]", safe_message)
            safe_message = _BEARER_PATTERN.sub("Bearer [REDACTED]", safe_message)
            safe_message = _SHOPIFY_TOKEN_PATTERN.sub("[REDACTED_TOKEN]", safe_message)
            safe_message = re.sub(r"https?://\S+", "[REDACTED_URL]", safe_message)
        diagnostics.append({
            "code": code if isinstance(code, str) else None,
            "path": safe_path,
            "message": safe_message,
        })
    return tuple(diagnostics)


async def request_oauth_token(shop_domain: str, data: dict[str, str]) -> dict[str, Any]:
    url = f"https://{shop_domain}/admin/oauth/access_token"
    started_at = time.monotonic()
    log_shopify_event(
        "request",
        method="POST",
        shop_domain=shop_domain,
        endpoint="/admin/oauth/access_token",
        content_type="application/x-www-form-urlencoded",
        timeout_seconds=settings.shopify_timeout_seconds,
        payload=data,
    )
    async with httpx.AsyncClient(timeout=settings.shopify_timeout_seconds) as client:
        try:
            response = await client.post(
                url,
                data=data,
                headers={"accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            log_shopify_event(
                "transport_error",
                shop_domain=shop_domain,
                endpoint="/admin/oauth/access_token",
                elapsed_ms=round((time.monotonic() - started_at) * 1000),
                error_type=type(exc).__name__,
            )
            raise ShopifyAPIError("shopify_unavailable") from exc
    try:
        response_body = response.json()
    except ValueError:
        response_body = None
    request_secrets = tuple(
        value
        for key, value in data.items()
        if _is_sensitive_log_key(key) and isinstance(value, str)
    )
    safe_response = response_body
    if isinstance(response_body, dict):
        safe_response = _redact_for_log(response_body, sensitive_values=request_secrets)
    elif response_body is not None:
        safe_response = {"format": "unexpected_json_type", "body_type": type(response_body).__name__}
    else:
        safe_response = {
            "format": "non_json",
            "body_length": len(getattr(response, "text", "")),
        }
    log_shopify_event(
        "response",
        shop_domain=shop_domain,
        endpoint="/admin/oauth/access_token",
        status_code=response.status_code,
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        content_type=getattr(response, "headers", {}).get("content-type"),
        body=safe_response,
    )
    if response.status_code >= 500:
        raise ShopifyAPIError("shopify_unavailable")
    if response.status_code >= 400:
        # Shopify's token endpoint returns OAuth error codes in its body. Keep
        # only an allowlisted code; never pass the provider body through because
        # it can contain request details we do not want to expose to the UI.
        reason_code = None
        body = response_body
        if isinstance(body, dict):
            candidate = body.get("error")
            if isinstance(candidate, str):
                reason_code = candidate.strip().casefold()
        if reason_code is None:
            response_text = getattr(response, "text", "")
            if isinstance(response_text, str):
                match = re.search(r"(?:Oauth error|OAuth error)\s+([a-z_]+)", response_text, re.IGNORECASE)
                if match:
                    reason_code = match.group(1).casefold()
        raise ShopifyAPIError(
            "shopify_authorization_failed",
            status_code=403,
            reason_code=reason_code,
        )
    body = response_body
    if body is None:
        raise ShopifyAPIError("shopify_invalid_response")
    if not isinstance(body, dict):
        raise ShopifyAPIError("shopify_invalid_response")
    return body


async def request_client_credentials_token(shop_domain: str) -> dict[str, Any]:
    """Exchange app credentials for a short-lived token for a configured dev store."""
    if settings.shopify_client_id is None or settings.shopify_client_secret is None:
        raise ShopifyAPIError("shopify_authorization_failed", status_code=503)
    return await request_oauth_token(
        shop_domain,
        {
            "grant_type": "client_credentials",
            "client_id": settings.shopify_client_id,
            "client_secret": settings.shopify_client_secret.get_secret_value(),
        },
    )


async def graphql(
    shop_domain: str,
    access_token: str,
    query: str,
    variables: dict[str, Any],
    *,
    diagnostic_context: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    api_version = settings.shopify_api_version
    if len(api_version) != 7 or api_version[4] != "-" or not api_version.replace("-", "").isdigit():
        raise ShopifyAPIError("shopify_api_version_invalid", status_code=503)
    operation_match = re.search(r"\b(query|mutation)\s+([A-Za-z_][A-Za-z0-9_]*)", query)
    operation_type = operation_match.group(1) if operation_match else "unknown"
    operation_name = operation_match.group(2) if operation_match else "anonymous"
    query_fingerprint = hashlib.sha256(query.encode("utf-8")).hexdigest()
    started_at = time.monotonic()
    safe_context = dict(diagnostic_context or {})
    log_shopify_api_event(
        "graphql_request",
        **safe_context,
        shop_domain=shop_domain,
        api_version=api_version,
        request_attempted=True,
        operation_type=operation_type,
        operation_name=operation_name,
        query_fingerprint=query_fingerprint,
        variable_names=sorted(variables.keys()),
        timeout_seconds=settings.shopify_timeout_seconds,
    )
    async with httpx.AsyncClient(timeout=settings.shopify_timeout_seconds) as client:
        try:
            response = await client.post(
                f"https://{shop_domain}/admin/api/{api_version}/graphql.json",
                headers={
                    "accept": "application/json",
                    "content-type": "application/json",
                    "x-shopify-access-token": access_token,
                },
                json={"query": query, "variables": variables},
            )
        except httpx.HTTPError as exc:
            log_shopify_api_event(
                "graphql_transport_error",
                **safe_context,
                shop_domain=shop_domain,
                api_version=api_version,
                operation_name=operation_name,
                query_fingerprint=query_fingerprint,
                elapsed_ms=round((time.monotonic() - started_at) * 1000),
                error_type=type(exc).__name__,
            )
            raise ShopifyAPIError("shopify_unavailable") from exc
    try:
        body = response.json()
    except ValueError:
        body = None
    errors = body.get("errors") if isinstance(body, dict) else None
    error_codes = sorted({
        error.get("extensions", {}).get("code")
        for error in errors
        if isinstance(error, dict)
        and isinstance(error.get("extensions"), dict)
        and isinstance(error.get("extensions", {}).get("code"), str)
    }) if isinstance(errors, list) else []
    diagnostics = _safe_graphql_diagnostics(
        errors,
        sensitive_values=(access_token,),
        include_messages=operation_name.startswith("SupportPilotProduct"),
    )
    response_headers = getattr(response, "headers", {})
    served_api_version = response_headers.get("x-shopify-api-version") if hasattr(response_headers, "get") else None
    extensions = body.get("extensions") if isinstance(body, dict) else None
    cost = extensions.get("cost") if isinstance(extensions, dict) else None
    safe_cost = None
    if isinstance(cost, dict):
        throttle = cost.get("throttleStatus")
        safe_cost = {
            "requested_query_cost": cost.get("requestedQueryCost"),
            "actual_query_cost": cost.get("actualQueryCost"),
            "throttle_status": {
                key: throttle.get(key)
                for key in ("maximumAvailable", "currentlyAvailable", "restoreRate")
                if isinstance(throttle, dict) and isinstance(throttle.get(key), (int, float))
            },
        }
    log_shopify_api_event(
        "graphql_response",
        level=logging.ERROR if response.status_code >= 400 or error_codes else logging.INFO,
        **safe_context,
        shop_domain=shop_domain,
        api_version=api_version,
        operation_name=operation_name,
        query_fingerprint=query_fingerprint,
        status_code=response.status_code,
        served_api_version=served_api_version,
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        request_id=response_headers.get("x-request-id") if hasattr(response_headers, "get") else None,
        graphql_error_count=len(errors) if isinstance(errors, list) else 0,
        graphql_error_codes=error_codes,
        graphql_errors=diagnostics,
        graphql_cost=safe_cost,
        data_present=isinstance(body, dict) and isinstance(body.get("data"), dict),
    )
    if response.status_code == 401:
        raise ShopifyAPIError("shopify_reauthorization_required", status_code=409)
    if response.status_code == 403:
        raise ShopifyAPIError("shopify_access_denied", status_code=403, diagnostics=diagnostics)
    if response.status_code == 429:
        raise ShopifyAPIError("shopify_rate_limited", status_code=429)
    if response.status_code >= 500:
        raise ShopifyAPIError("shopify_unavailable")
    if response.status_code >= 400:
        if isinstance(errors, list) and errors:
            if "THROTTLED" in error_codes:
                raise ShopifyAPIError("shopify_rate_limited", status_code=429, diagnostics=diagnostics)
            if "ACCESS_DENIED" in error_codes:
                raise ShopifyAPIError("shopify_access_denied", status_code=403, diagnostics=diagnostics)
            raise ShopifyAPIError("shopify_graphql_error", status_code=422, diagnostics=diagnostics)
        raise ShopifyAPIError("shopify_request_rejected", status_code=502)
    if body is None:
        raise ShopifyAPIError("shopify_invalid_response")
    if not isinstance(body, dict):
        raise ShopifyAPIError("shopify_invalid_response")
    if body.get("errors"):
        if "THROTTLED" in error_codes:
            raise ShopifyAPIError("shopify_rate_limited", status_code=429, diagnostics=diagnostics)
        if "ACCESS_DENIED" in error_codes:
            raise ShopifyAPIError("shopify_access_denied", status_code=403, diagnostics=diagnostics)
        raise ShopifyAPIError("shopify_graphql_error", status_code=422, diagnostics=diagnostics)
    data = body.get("data")
    if not isinstance(data, dict):
        raise ShopifyAPIError("shopify_invalid_response")
    return data


CURRENT_APP_SCOPES_QUERY = """
query SupportPilotCurrentAppScopes {
  currentAppInstallation {
    accessScopes { handle }
  }
}
"""


async def fetch_current_app_scopes(shop_domain: str, access_token: str) -> list[str]:
    """Read actual installation grants when Shopify omits token response scopes."""
    data = await graphql(shop_domain, access_token, CURRENT_APP_SCOPES_QUERY, {})
    installation = data.get("currentAppInstallation")
    if not isinstance(installation, dict):
        raise ShopifyAPIError("shopify_invalid_response")
    scopes = installation.get("accessScopes")
    if not isinstance(scopes, list):
        raise ShopifyAPIError("shopify_invalid_response")
    handles = {
        item.get("handle")
        for item in scopes
        if isinstance(item, dict) and isinstance(item.get("handle"), str) and item["handle"]
    }
    return sorted(handles)


def parse_scope_list(scope_value: Any) -> list[str]:
    if not isinstance(scope_value, str):
        return []
    return sorted({scope.strip() for scope in scope_value.split(",") if scope.strip()})


def effective_shopify_scopes(granted_scopes: list[str] | set[str] | tuple[str, ...]) -> set[str]:
    """Expand Shopify write grants to the read access they also provide.

    Keep the raw grants for persistence and display. This expanded set is used
    only when deciding whether the connector can perform its required reads.
    """
    effective = set(granted_scopes)
    if "write_orders" in effective:
        effective.add("read_orders")
    if "write_customers" in effective:
        effective.add("read_customers")
    if "write_products" in effective:
        effective.add("read_products")
    return effective


async def resolve_token_scopes(shop_domain: str, token: dict[str, Any]) -> tuple[list[str], str]:
    """Prefer token scope metadata, then verify actual installation grants via GraphQL."""
    scopes = parse_scope_list(token.get("scope"))
    if scopes:
        return scopes, "token_response"
    access_token = token.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        return [], "token_response_missing_access_token"
    return await fetch_current_app_scopes(shop_domain, access_token), "current_app_installation"


ORDERS_QUERY = """
query SupportPilotOrders($query: String!, $first: Int!, $after: String) {
  orders(first: $first, after: $after, query: $query, sortKey: PROCESSED_AT, reverse: true) {
    nodes {
      id
      name
      createdAt
      displayFinancialStatus
      displayFulfillmentStatus
      cancelledAt
      closed
      returnStatus
      currentTotalPriceSet { shopMoney { amount currencyCode } }
      customer { id displayName email }
      fulfillments(first: 5) {
        trackingInfo { company number url }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""


ORDER_PAGE_QUERY = """
query SupportPilotOrderPage($first: Int!, $after: String) {
  orders(first: $first, after: $after, sortKey: CREATED_AT, reverse: true) {
    nodes {
      id
      name
      createdAt
      displayFinancialStatus
      displayFulfillmentStatus
      currentTotalPriceSet { shopMoney { amount currencyCode } }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""


async def fetch_order_page(
    shop_domain: str,
    access_token: str,
    *,
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    """Fetch one cursor-paginated page without customer PII."""
    data = await graphql(
        shop_domain,
        access_token,
        ORDER_PAGE_QUERY,
        {"first": limit, "after": cursor},
    )
    orders = data.get("orders")
    if not isinstance(orders, dict) or not isinstance(orders.get("nodes"), list):
        raise ShopifyAPIError("shopify_invalid_response")
    page_info = orders.get("pageInfo")
    if not isinstance(page_info, dict):
        raise ShopifyAPIError("shopify_invalid_response")
    return {"nodes": orders["nodes"], "page_info": page_info}


async def fetch_orders(
    shop_domain: str,
    access_token: str,
    *,
    search_query: str,
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    data = await graphql(
        shop_domain,
        access_token,
        ORDERS_QUERY,
        {"query": search_query, "first": limit, "after": cursor},
    )
    orders = data.get("orders")
    if not isinstance(orders, dict) or not isinstance(orders.get("nodes"), list):
        raise ShopifyAPIError("shopify_invalid_response")
    page_info = orders.get("pageInfo")
    if not isinstance(page_info, dict):
        raise ShopifyAPIError("shopify_invalid_response")
    return {"nodes": orders["nodes"], "page_info": page_info}
