"""Provider-neutral product catalog values."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CatalogImage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    url: HttpUrl
    alt_text: str | None = Field(default=None, max_length=500)


class CatalogVariantSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    external_variant_id: str = Field(min_length=1, max_length=512)
    title: str = Field(min_length=1, max_length=255)
    sku: str | None = Field(default=None, max_length=255)
    attributes: dict[str, str] = Field(default_factory=dict)
    price: Decimal = Field(ge=0, max_digits=20, decimal_places=4)
    compare_at_price: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=4)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    availability: Literal["available", "unavailable", "unknown"] = "unknown"
    provider_updated_at: datetime | None = None


class CatalogPriceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    price: Decimal = Field(ge=0, max_digits=20, decimal_places=4)
    compare_at_price: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=4)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    provider_updated_at: datetime | None = None


class CatalogProductSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    external_product_id: str = Field(min_length=1, max_length=512)
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=20000)
    brand: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=255)
    images: list[CatalogImage] = Field(default_factory=list, max_length=20)
    canonical_url: HttpUrl | None = None
    status: Literal["active", "draft", "archived", "unknown"] = "unknown"
    specifications: dict[str, str] = Field(default_factory=dict)
    variants: list[CatalogVariantSnapshot] = Field(default_factory=list, max_length=2048)
    provider_updated_at: datetime | None = None


class CatalogProductPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[CatalogProductSnapshot]
    next_cursor: str | None = Field(default=None, max_length=2048)
    has_more: bool
