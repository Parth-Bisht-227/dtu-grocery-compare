"""Provider-independent domain models."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Provider(str, Enum):
    BLINKIT = "Blinkit"
    INSTAMART = "Instamart"


class NormalizedQuantity(BaseModel):
    """A quantity converted to one base unit (g, ml, pcs, or combo)."""

    model_config = ConfigDict(frozen=True)

    value: Decimal = Field(gt=0, description="Base-unit amount per pack item")
    unit: Literal["g", "ml", "pcs", "combo"]
    pack_count: int = Field(default=1, ge=1)
    explicit_pack: bool = False

    @property
    def total_value(self) -> Decimal:
        return self.value * self.pack_count


class Product(BaseModel):
    """The normalized boundary shared by both marketplace adapters."""

    model_config = ConfigDict(frozen=True)

    provider: Provider
    title: str = Field(min_length=1)
    quantity_raw: str
    quantity: NormalizedQuantity | None = None
    price: Decimal = Field(gt=0)
    mrp: Decimal | None = Field(default=None, gt=0)
    image_url: str | None = None
    product_url: str | None = None
    provider_product_id: str | None = None


class ProductMatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    blinkit: Product
    instamart: Product
    score: float = Field(ge=0, le=100)

    @property
    def cheaper_provider(self) -> Provider | None:
        if self.blinkit.price == self.instamart.price:
            return None
        return (
            Provider.BLINKIT
            if self.blinkit.price < self.instamart.price
            else Provider.INSTAMART
        )

    @property
    def savings(self) -> Decimal:
        return abs(self.blinkit.price - self.instamart.price)


class SearchOutcome(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    query: str
    products: dict[Provider, list[Product]]
    errors: dict[Provider, str] = Field(default_factory=dict)
    matches: list[ProductMatch] = Field(default_factory=list)
    unmatched: dict[Provider, list[Product]] = Field(default_factory=dict)

