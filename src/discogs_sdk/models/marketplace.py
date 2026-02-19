from __future__ import annotations

from typing import Any

from pydantic import Field

from discogs_sdk.models._common import Condition, CurrencyCode, Price, SDKModel, SleeveCondition, UserSummary


class ListingRelease(SDKModel):
    id: int | None = None
    catalog_number: str | None = None
    description: str | None = None
    resource_url: str | None = None
    thumbnail: str | None = None
    year: int | None = None


class OriginalPrice(SDKModel):
    currency_code: CurrencyCode | str | None = Field(default=None, validation_alias="curr_abbr")
    currency_id: int | None = Field(default=None, validation_alias="curr_id")
    formatted: str | None = None
    value: float | None = None


class ShippingInfo(SDKModel):
    currency: CurrencyCode | str | None = None
    method: str | None = None
    value: float | None = None


class Listing(SDKModel):
    id: int
    allow_offers: bool | None = None
    audio: bool | None = None
    comments: str | None = None
    condition: Condition | str | None = None
    original_price: OriginalPrice | None = None
    posted: str | None = None
    price: Price | None = None
    release: ListingRelease | None = None
    resource_url: str | None = None
    seller: UserSummary | None = None
    shipping_price: Price | None = None
    ships_from: str | None = None
    sleeve_condition: SleeveCondition | str | None = None
    status: str | None = None
    uri: str | None = None


class OrderItem(SDKModel):
    id: int | None = None
    price: Price | None = None
    release: ListingRelease | None = None


class Order(SDKModel):
    id: str
    additional_instructions: str | None = None
    archived: bool | None = None
    buyer: UserSummary | None = None
    created: str | None = None
    fee: Price | None = None
    items: list[OrderItem] | None = None
    last_activity: str | None = None
    messages_url: str | None = None
    next_status: list[str] | None = None
    resource_url: str | None = None
    seller: UserSummary | None = None
    shipping_address: str | None = None
    shipping: ShippingInfo | None = None
    status: str | None = None
    total: Price | None = None
    uri: str | None = None


class OrderMessage(SDKModel):
    actor: UserSummary | None = None
    from_user: UserSummary | None = Field(default=None, alias="from")
    message: str | None = None
    order: dict[str, Any] | None = None
    status_id: int | None = None
    subject: str | None = None
    timestamp: str | None = None
    type: str | None = None


class Fee(SDKModel):
    currency: CurrencyCode | str | None = None
    value: float
