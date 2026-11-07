from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, model_validator


class CommerceActionCreate(BaseModel):
    ticket_id: UUID
    order_number: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60, pattern=r"^#?[A-Za-z0-9-]+$")]
    action_type: Literal["refund", "cancel"]
    provider: Literal["mock", "shopify"] = "mock"
    refund_amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    cancel_refund: bool = False
    cancel_restock: bool = False
    cancel_notify_customer: bool = False
    cancellation_reason: Literal["CUSTOMER", "DECLINED", "FRAUD", "INVENTORY", "STAFF", "OTHER"] = "CUSTOMER"
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]

    @model_validator(mode="after")
    def amount_matches_action(self):
        if self.action_type == "refund" and self.refund_amount is None:
            raise ValueError("refund_amount is required for a refund request")
        if self.action_type == "cancel" and self.refund_amount is not None:
            raise ValueError("refund_amount must be omitted for a cancellation request")
        if self.provider == "shopify" and self.action_type != "cancel":
            raise ValueError("Only cancellations can currently execute against Shopify")
        if self.action_type != "cancel" and any((self.cancel_refund, self.cancel_restock, self.cancel_notify_customer)):
            raise ValueError("Cancellation options can only be set for cancellation requests")
        return self


class CommerceActionOut(BaseModel):
    id: UUID
    ticket_id: UUID
    requested_by_user_id: UUID | None
    requested_by_name: str
    action_type: Literal["refund", "cancel"]
    provider: Literal["mock", "shopify"]
    shopify_order_id: str
    order_number: str
    order_total: Decimal
    currency: str
    refund_amount: Decimal | None
    cancel_refund: bool
    cancel_restock: bool
    cancel_notify_customer: bool
    cancellation_reason: str
    reason: str
    approval_status: Literal["pending", "approved", "rejected", "expired", "cancelled"]
    execution_status: Literal["not_started", "queued", "running", "succeeded", "failed"]
    execution_attempt_count: int
    execution_result: dict[str, Any]
    execution_error_code: str | None
    correlation_id: str | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    reviewed_by_user_id: UUID | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    cancelled_by_user_id: UUID | None
    cancelled_at: datetime | None
    execution_started_at: datetime | None
    execution_completed_at: datetime | None


class CommerceActionPage(BaseModel):
    items: list[CommerceActionOut]
    total: int
    limit: int
    offset: int


class CommerceActionAuditOut(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    actor_name: str | None
    event_type: str
    details: dict[str, Any]
    created_at: datetime


class CommerceActionAuditPage(BaseModel):
    items: list[CommerceActionAuditOut]
    total: int
    limit: int
    offset: int
