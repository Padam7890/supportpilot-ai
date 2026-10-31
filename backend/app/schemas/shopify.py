from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class ShopifyStatusOut(BaseModel):
    configured: bool
    connected: bool
    client_credentials_available: bool = False
    configured_store_domain: str | None = None
    shop_domain: str | None = None
    granted_scopes: list[str] = Field(default_factory=list)
    connected_at: datetime | None = None
    access_token_expires_at: datetime | None = None
    reconnect_required: bool = False


class ShopifyCustomerOut(BaseModel):
    display_name: str | None
    email: EmailStr
    verified_by: Literal["order_number_and_email"]


class ShopifyTrackingOut(BaseModel):
    company: str | None
    number: str | None
    url: str | None


class ShopifyOrderOut(BaseModel):
    id: str
    order_number: str
    created_at: datetime
    financial_status: str | None
    fulfillment_status: str | None
    total_amount: str
    currency: str
    tracking: list[ShopifyTrackingOut]
    cancelled_at: datetime | None = None
    closed: bool | None = None
    return_status: str | None = None


class ShopifyOrderSummaryOut(BaseModel):
    id: str
    order_number: str
    created_at: datetime
    financial_status: str | None
    fulfillment_status: str | None
    total_amount: str
    currency: str


class ShopifyOrderPageOut(BaseModel):
    items: list[ShopifyOrderSummaryOut]
    has_next_page: bool
    next_cursor: str | None


class ShopifyOrderLookupOut(BaseModel):
    customer: ShopifyCustomerOut
    matched_order: ShopifyOrderOut
    recent_orders: list[ShopifyOrderOut]
    has_next_page: bool
    next_cursor: str | None


class ShopifyIntegrationEventOut(BaseModel):
    status: Literal["connected", "disconnected"]
    message: str
    shop_domain: str | None = None


class ShopifyLookupRequest(BaseModel):
    customer_email: EmailStr
    order_number: str = Field(min_length=1, max_length=60, pattern=r"^#?[A-Za-z0-9-]+$")
    limit: int = Field(default=10, ge=1, le=20)
    cursor: str | None = Field(default=None, max_length=512)
