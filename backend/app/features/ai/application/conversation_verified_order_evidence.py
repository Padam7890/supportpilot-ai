"""Minimize server-authorized Shopify results for deterministic reply drafts."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.features.ai.application.conversation_response_evidence import (
    EvidenceItem,
    ResponseEvidence,
)
from app.schemas.shopify import ShopifyOrderOut

OrderText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class OrderTrackingFact(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    company: OrderText | None = None
    number: OrderText | None = None

    @field_validator("company", "number", mode="before")
    @classmethod
    def exclude_private_or_unsafe_text(cls, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        value = value.strip()
        if not 1 <= len(value) <= 100 or any(character in value for character in "\r\n<>@"):
            return None
        if "://" in value:
            return None
        return value


class AuthorizedOrderSnapshot(BaseModel):
    """Only instantiate from the server lookup or the encrypted execution field."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    order_number: str = Field(min_length=1, max_length=100, pattern=r"^[^\r\n<>@]+$")
    financial_status: str | None = Field(default=None, pattern=r"^[a-zA-Z_ -]{1,40}$")
    fulfillment_status: str | None = Field(default=None, pattern=r"^[a-zA-Z_ -]{1,40}$")
    return_status: str | None = Field(default=None, pattern=r"^[a-zA-Z_ -]{1,40}$")
    total_amount: str | None = Field(default=None, pattern=r"^[0-9]{1,20}(\.[0-9]{1,8})?$")
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    cancelled_at: str | None = Field(default=None, max_length=40, pattern=r"^[0-9TtZz:+. -]+$")
    tracking: list[OrderTrackingFact] = Field(default_factory=list, max_length=3)

    @classmethod
    def from_authorized_lookup(cls, order: ShopifyOrderOut) -> "AuthorizedOrderSnapshot":
        return cls(
            order_number=order.order_number,
            financial_status=order.financial_status,
            fulfillment_status=order.fulfillment_status,
            return_status=order.return_status,
            total_amount=order.total_amount,
            currency=order.currency,
            cancelled_at=order.cancelled_at.isoformat() if order.cancelled_at else None,
            tracking=[
                OrderTrackingFact(company=item.company, number=item.number)
                for item in order.tracking[:3]
            ],
        )

    @field_validator("tracking", mode="before")
    @classmethod
    def bound_legacy_tracking(cls, value: object) -> object:
        return value[:3] if isinstance(value, list) else value

    def as_evidence(self) -> ResponseEvidence:
        facts = [f"I checked your verified order {self.order_number}."]
        if self.cancelled_at:
            facts.append("Shopify shows this order was cancelled.")
        for label, status in (
            ("Payment", self.financial_status),
            ("Fulfillment", self.fulfillment_status if not self.cancelled_at else None),
            ("Return", self.return_status),
        ):
            if status:
                facts.append(f"{label} status: {status.replace('_', ' ').lower()}.")
        if self.total_amount and self.currency:
            facts.append(f"Order total: {self.total_amount} {self.currency}.")
        for entry in self.tracking:
            details = [value for value in (entry.company, entry.number) if value]
            if details:
                facts.append(f"Tracking details: {' · '.join(details)}.")
        return ResponseEvidence(
            (EvidenceItem("verified_order", " ".join(facts), self.order_number),),
            "verified",
        )
