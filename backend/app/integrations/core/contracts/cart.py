"""Optional cart and checkout contracts. Providers may omit these capabilities."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CartLine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    external_variant_id: str = Field(min_length=1, max_length=512)
    quantity: int = Field(ge=1, le=100)


class CartSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    external_cart_id: str = Field(min_length=1, max_length=512)
    checkout_url: HttpUrl | None = None
    total: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=4)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
