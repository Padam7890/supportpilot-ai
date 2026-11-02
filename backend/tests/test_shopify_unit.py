import hashlib
import hmac
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.integrations.providers.shopify.security import (
    hash_oauth_state,
    make_authorization_url,
    normalize_shop_domain,
    validate_callback_timestamp,
    verify_callback_hmac,
)
from app.services.shopify_order_lookup import shopify_query_fingerprint


@pytest.mark.parametrize(
    ("granted", "expected"),
    [
        (["read_customers", "write_orders"], {"read_customers", "write_orders", "read_orders"}),
        (["write_customers"], {"write_customers", "read_customers"}),
        (["read_orders"], {"read_orders"}),
    ],
)
def test_effective_shopify_scopes_include_only_implied_read_permissions(granted, expected):
    from app.integrations.providers.shopify.client import effective_shopify_scopes

    assert effective_shopify_scopes(granted) == expected


def test_write_orders_and_read_customers_satisfy_connector_read_requirements():
    from app.integrations.providers.shopify.client import effective_shopify_scopes
    from app.integrations.providers.shopify.security import REQUIRED_SCOPES

    actual_grants = ["read_customers", "write_orders"]

    assert set(REQUIRED_SCOPES).issubset(effective_shopify_scopes(actual_grants))
    assert actual_grants == ["read_customers", "write_orders"]


def test_shop_domain_validation_blocks_host_confusion():
    assert normalize_shop_domain(" Demo-Shop.myshopify.com ") == "demo-shop.myshopify.com"
    for invalid in (
        "https://demo-shop.myshopify.com",
        "demo-shop.myshopify.com.attacker.example",
        "demo_shop.myshopify.com",
        "demo-shop.example.com",
    ):
        with pytest.raises(ValueError):
            normalize_shop_domain(invalid)


def test_authorization_url_requests_only_read_scopes_and_unique_state(monkeypatch):
    monkeypatch.setattr(settings, "shopify_client_id", "client-id")
    monkeypatch.setattr(
        settings,
        "shopify_redirect_uri",
        "https://support.example/api/integrations/shopify/callback",
    )
    first = make_authorization_url("demo-shop.myshopify.com", "state-one")
    second = make_authorization_url("demo-shop.myshopify.com", "state-two")
    first_params = parse_qs(urlsplit(first).query)
    second_params = parse_qs(urlsplit(second).query)
    assert first_params["scope"] == ["read_orders,read_customers,read_products"]
    assert first_params["redirect_uri"] == [
        "https://support.example/api/integrations/shopify/callback"
    ]
    assert first_params["state"] != second_params["state"]
    assert hash_oauth_state("state-one") != "state-one"


def test_callback_hmac_is_signed_and_timestamp_is_bounded(monkeypatch):
    secret = "shopify-client-secret"
    monkeypatch.setattr(settings, "shopify_client_secret", SecretStr(secret))
    items = [
        ("code", "one-time-code"),
        ("shop", "demo-shop.myshopify.com"),
        ("state", "nonce"),
        ("timestamp", str(int(time.time()))),
    ]
    canonical = "&".join(f"{key}={value}" for key, value in sorted(items))
    signature = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    assert verify_callback_hmac([*items, ("hmac", signature)], signature)
    assert not verify_callback_hmac([*items, ("hmac", signature)], "0" * 64)
    assert validate_callback_timestamp(str(int(time.time())))
    assert not validate_callback_timestamp(str(int(time.time()) - 700))


def test_shopify_query_fingerprint_is_keyed_and_contains_no_customer_email(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "unit-test-secret-for-fingerprint")
    fingerprint = shopify_query_fingerprint(
        "demo-store.myshopify.com", "Morgan@example.com", "#1001"
    )
    assert fingerprint == shopify_query_fingerprint(
        "demo-store.myshopify.com", "morgan@example.com", "#1001"
    )
    assert fingerprint != shopify_query_fingerprint(
        "demo-store.myshopify.com", "another@example.com", "#1001"
    )
    assert len(fingerprint) == 64
    assert "morgan@example.com" not in fingerprint


def test_shopify_credential_encryption_round_trip(monkeypatch):
    pytest.importorskip("cryptography")
    from cryptography.fernet import Fernet

    from app.integrations.providers.shopify.security import decrypt_credential, encrypt_credential

    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(settings, "shopify_encryption_key", SecretStr(key))
    raw = "shpat_private-token"
    encrypted = encrypt_credential(raw)
    assert encrypted != raw
    assert raw not in encrypted
    assert decrypt_credential(encrypted) == raw


@pytest.mark.anyio
async def test_client_credentials_exchange_is_server_side_and_requests_no_extra_scope(
    monkeypatch, caplog
):
    from app.integrations.providers.shopify import client as shopify_client

    monkeypatch.setattr(settings, "shopify_client_id", "configured-client")
    monkeypatch.setattr(settings, "shopify_client_secret", SecretStr("configured-secret"))
    calls = []

    class Response:
        status_code = 200

        def __init__(self):
            self.headers = {"content-type": "application/json"}

        @staticmethod
        def json():
            return {
                "access_token": "private-token",
                "refresh_token": "private-refresh-token",
                "expires_in": 86400,
                "scope": "read_orders,read_customers",
            }

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, data, headers):
            calls.append((url, data, headers))
            return Response()

    monkeypatch.setattr(shopify_client.httpx, "AsyncClient", Client)
    with caplog.at_level("INFO", logger=shopify_client.__name__):
        response = await shopify_client.request_client_credentials_token(
            "configured-store.myshopify.com"
        )

    assert response["access_token"] == "private-token"
    assert '"event": "request"' in caplog.text
    assert '"event": "response"' in caplog.text
    assert '"client_secret": "[REDACTED]"' in caplog.text
    assert '"access_token": "[REDACTED]"' in caplog.text
    assert '"refresh_token": "[REDACTED]"' in caplog.text
    assert "configured-secret" not in caplog.text
    assert "private-token" not in caplog.text
    assert "private-refresh-token" not in caplog.text
    assert "read_orders,read_customers" in caplog.text
    assert calls == [
        (
            "https://configured-store.myshopify.com/admin/oauth/access_token",
            {
                "grant_type": "client_credentials",
                "client_id": "configured-client",
                "client_secret": "configured-secret",
            },
            {"accept": "application/json"},
        )
    ]


@pytest.mark.anyio
async def test_client_credentials_exchange_preserves_only_shopify_error_code(monkeypatch, caplog):
    from app.integrations.providers.shopify import client as shopify_client

    monkeypatch.setattr(settings, "shopify_client_id", "configured-client")
    monkeypatch.setattr(settings, "shopify_client_secret", SecretStr("configured-secret"))

    class Response:
        status_code = 403

        @staticmethod
        def json():
            return {
                "error": "shop_not_permitted",
                "error_description": "contains provider details that should not be shown",
            }

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(shopify_client.httpx, "AsyncClient", Client)
    with (
        caplog.at_level("INFO", logger=shopify_client.__name__),
        pytest.raises(shopify_client.ShopifyAPIError) as error,
    ):
        await shopify_client.request_client_credentials_token("configured-store.myshopify.com")

    assert error.value.code == "shopify_authorization_failed"
    assert error.value.reason_code == "shop_not_permitted"
    assert "provider details" not in str(error.value)
    assert '"status_code": 403' in caplog.text
    assert '"error": "shop_not_permitted"' in caplog.text
    assert "contains provider details that should not be shown" in caplog.text
    assert "configured-secret" not in caplog.text

    from app.services.shopify_errors import to_api_error

    api_error = to_api_error(error.value)
    assert api_error.status_code == 403
    assert "same Shopify organization" in api_error.detail
    assert "provider details" not in api_error.detail


@pytest.mark.anyio
async def test_empty_token_scope_falls_back_to_actual_installation_scopes(monkeypatch):
    from app.integrations.providers.shopify import client as shopify_client

    calls = []

    async def fake_graphql(shop_domain, access_token, query, variables):
        calls.append((shop_domain, access_token, query, variables))
        return {
            "currentAppInstallation": {
                "accessScopes": [{"handle": "read_orders"}, {"handle": "read_customers"}],
            }
        }

    monkeypatch.setattr(shopify_client, "graphql", fake_graphql)
    scopes, source = await shopify_client.resolve_token_scopes(
        "configured-store.myshopify.com",
        {"access_token": "temporary-token", "scope": ""},
    )

    assert scopes == ["read_customers", "read_orders"]
    assert source == "current_app_installation"
    assert calls[0][0:2] == ("configured-store.myshopify.com", "temporary-token")
    assert "currentAppInstallation" in calls[0][2]


@pytest.mark.anyio
async def test_empty_token_scope_and_empty_installation_scopes_remain_empty(monkeypatch):
    from app.integrations.providers.shopify import client as shopify_client

    async def fake_graphql(*_args):
        return {"currentAppInstallation": {"accessScopes": []}}

    monkeypatch.setattr(shopify_client, "graphql", fake_graphql)
    scopes, source = await shopify_client.resolve_token_scopes(
        "configured-store.myshopify.com",
        {"access_token": "temporary-token", "scope": ""},
    )

    assert scopes == []
    assert source == "current_app_installation"


@pytest.mark.anyio
async def test_fetch_order_page_maps_shopify_connection_page_without_customer_fields(monkeypatch):
    from app.integrations.providers.shopify import client as shopify_client

    calls = []

    async def fake_graphql(shop_domain, access_token, query, variables):
        calls.append((shop_domain, access_token, query, variables))
        return {
            "orders": {
                "nodes": [
                    {
                        "id": "gid://shopify/Order/1001",
                        "name": "#1001",
                        "createdAt": "2026-10-30T12:00:00Z",
                        "displayFinancialStatus": "PAID",
                        "displayFulfillmentStatus": "FULFILLED",
                        "currentTotalPriceSet": {
                            "shopMoney": {"amount": "42.50", "currencyCode": "USD"}
                        },
                    }
                ],
                "pageInfo": {"hasNextPage": True, "endCursor": "opaque-next"},
            }
        }

    monkeypatch.setattr(shopify_client, "graphql", fake_graphql)
    page = await shopify_client.fetch_order_page(
        "configured-store.myshopify.com", "private-token", limit=25, cursor="opaque-prev"
    )

    assert page["nodes"][0]["name"] == "#1001"
    assert page["page_info"] == {"hasNextPage": True, "endCursor": "opaque-next"}
    assert calls[0][3] == {"first": 25, "after": "opaque-prev"}
    assert "customer" not in calls[0][2]


@pytest.mark.anyio
async def test_graphql_logs_provider_error_codes_without_tokens_or_response_text(
    monkeypatch, caplog
):
    from app.integrations.providers.shopify import client as shopify_client

    class Response:
        status_code = 200

        def __init__(self):
            self.headers = {"x-request-id": "shopify-request-123"}

        @staticmethod
        def json():
            return {
                "data": None,
                "errors": [
                    {
                        "message": "No order access for private.customer@example.test",
                        "extensions": {"code": "ACCESS_DENIED"},
                    }
                ],
            }

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(shopify_client.httpx, "AsyncClient", Client)
    with (
        caplog.at_level("INFO", logger=shopify_client.__name__),
        pytest.raises(shopify_client.ShopifyAPIError) as error,
    ):
        await shopify_client.graphql(
            "configured-store.myshopify.com",
            "private-shopify-token",
            "query SupportPilotOrderPage($first: Int!) { orders(first: $first) { nodes { id } } }",
            {"first": 25, "customer_email": "private.customer@example.test"},
        )

    assert '"event": "graphql_response"' in caplog.text
    assert '"operation_name": "SupportPilotOrderPage"' in caplog.text
    assert '"graphql_error_codes": ["ACCESS_DENIED"]' in caplog.text
    assert '"status_code": 200' in caplog.text
    assert "shopify-request-123" in caplog.text
    assert error.value.code == "shopify_access_denied"
    assert error.value.diagnostics[0]["code"] == "ACCESS_DENIED"
    assert error.value.diagnostics[0]["message"] is None
    assert "private-shopify-token" not in caplog.text
    assert "private.customer@example.test" not in caplog.text
    assert "No order access" not in caplog.text


@pytest.mark.anyio
async def test_graphql_validation_errors_are_not_misreported_as_missing_scopes(monkeypatch, caplog):
    from app.integrations.providers.shopify import client as shopify_client

    class Response:
        status_code = 200

        def __init__(self):
            self.headers = {"x-shopify-api-version": "2026-10", "x-request-id": "query-error-123"}

        @staticmethod
        def json():
            return {
                "errors": [
                    {
                        "message": "Field doesNotExist is not defined on Product",
                        "path": ["products"],
                        "extensions": {"code": "GRAPHQL_VALIDATION_FAILED"},
                    }
                ],
            }

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(shopify_client.httpx, "AsyncClient", Client)
    with (
        caplog.at_level("INFO", logger=shopify_client.__name__),
        pytest.raises(shopify_client.ShopifyAPIError) as error,
    ):
        await shopify_client.graphql(
            "configured-store.myshopify.com",
            "private-shopify-token",
            "query SupportPilotProducts { products(first: 1) { nodes { id } } }",
            {},
            diagnostic_context={
                "organization_id": "tenant-1",
                "connection_id": "connection-1",
                "job_id": "job-1",
                "job_status": "running",
            },
        )

    assert error.value.code == "shopify_graphql_error"
    assert error.value.status_code == 422
    assert error.value.diagnostics[0]["code"] == "GRAPHQL_VALIDATION_FAILED"
    assert '"served_api_version": "2026-10"' in caplog.text
    assert '"request_attempted": true' in caplog.text
    assert '"organization_id": "tenant-1"' in caplog.text
    assert '"connection_id": "connection-1"' in caplog.text
    assert '"job_id": "job-1"' in caplog.text
    assert '"job_status": "running"' in caplog.text
    assert "Field doesNotExist is not defined on Product" in caplog.text
    assert "private-shopify-token" not in caplog.text


def test_shopify_cancellation_rejects_missing_scope_and_ineligible_orders():
    from app.integrations.providers.shopify.actions import (
        ShopifyOrderActionError,
        check_cancellation_eligibility,
        check_cancellation_scope,
    )

    with pytest.raises(ShopifyOrderActionError, match="shopify_cancel_permission_denied"):
        check_cancellation_scope(["read_customers", "read_orders"])

    for order, expected in [
        ({"cancelledAt": "2026-10-30T12:00:00Z"}, "shopify_order_already_cancelled"),
        ({"closed": True}, "shopify_order_not_cancelable"),
        ({"returnStatus": "IN_PROGRESS"}, "shopify_order_has_active_return"),
    ]:
        with pytest.raises(ShopifyOrderActionError, match=expected):
            check_cancellation_eligibility(order)


@pytest.mark.anyio
async def test_shopify_cancellation_passes_explicit_consequences_and_returns_safe_result(
    monkeypatch,
):
    from app.integrations.providers.shopify import actions as shopify_actions

    calls = []

    async def fake_graphql(shop_domain, access_token, query, variables):
        calls.append((shop_domain, access_token, variables))
        return {
            "orderCancel": {
                "jobResult": {
                    "id": "gid://shopify/OrderCancelJobResult/123",
                    "done": True,
                    "status": "SUCCEEDED",
                    "errors": [],
                    "order": {
                        "id": "gid://shopify/Order/1001",
                        "name": "#1001",
                        "cancelledAt": "2026-10-31T10:00:00Z",
                    },
                },
                "orderCancelUserErrors": [],
            }
        }

    monkeypatch.setattr(shopify_actions, "graphql", fake_graphql)
    result = await shopify_actions.cancel_shopify_order(
        shop_domain="configured-store.myshopify.com",
        access_token="private-token",
        order_id="gid://shopify/Order/1001",
        notify_customer=False,
        refund=False,
        restock=False,
        reason="CUSTOMER",
        staff_note="Customer requested cancellation",
        poll_interval_seconds=0,
    )

    assert calls[0][2]["notifyCustomer"] is False
    assert calls[0][2]["refundMethod"] == {"originalPaymentMethodsRefund": False}
    assert calls[0][2]["restock"] is False
    assert result["provider"] == "shopify"
    assert result["order_id"] == "gid://shopify/Order/1001"
    assert "private-token" not in str(result)


@pytest.mark.anyio
async def test_shopify_cancellation_maps_permission_and_provider_errors(monkeypatch):
    from app.integrations.providers.shopify import actions as shopify_actions
    from app.integrations.providers.shopify.client import ShopifyAPIError

    async def forbidden(*_args, **_kwargs):
        raise ShopifyAPIError("shopify_scope_or_data_access_required", status_code=403)

    monkeypatch.setattr(shopify_actions, "graphql", forbidden)
    with pytest.raises(
        shopify_actions.ShopifyOrderActionError, match="shopify_cancel_permission_denied"
    ):
        await shopify_actions.cancel_shopify_order(
            shop_domain="configured-store.myshopify.com",
            access_token="private-token",
            order_id="gid://shopify/Order/1001",
            notify_customer=False,
            refund=False,
            restock=False,
            reason="CUSTOMER",
            staff_note="Cancel request",
        )

    async def unavailable(*_args, **_kwargs):
        raise ShopifyAPIError("shopify_unavailable", status_code=502)

    monkeypatch.setattr(shopify_actions, "graphql", unavailable)
    with pytest.raises(
        shopify_actions.ShopifyOrderActionError, match="shopify_cancel_provider_error"
    ):
        await shopify_actions.cancel_shopify_order(
            shop_domain="configured-store.myshopify.com",
            access_token="private-token",
            order_id="gid://shopify/Order/1001",
            notify_customer=False,
            refund=False,
            restock=False,
            reason="CUSTOMER",
            staff_note="Cancel request",
        )
