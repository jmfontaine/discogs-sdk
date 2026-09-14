from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, Field

from discogs_sdk.models._common import (
    Condition,
    CurrencyCode,
    Price,
    SDKModel,
    SleeveCondition,
    UserSummary,
)

# Carriers the order-tracking endpoint accepts, per the Marketplace reference.
TrackingCarrier = Literal[
    "UPS",
    "USPS",
    "DHL",
    "Deutsche Post",
    "La Poste",
    "Royal Mail",
    "PostNL",
    "DHL Germany",
    "Other",
]


class ListingRelease(SDKModel):
    id: int | None = None
    artist: str | None = None
    catalog_number: str | None = None
    description: str | None = None
    format: str | None = None
    resource_url: str | None = None
    thumbnail: str | None = None
    title: str | None = None
    year: int | None = None


class OriginalPrice(SDKModel):
    currency_code: CurrencyCode | str | None = Field(
        default=None, validation_alias="curr_abbr"
    )
    currency_id: int | None = Field(default=None, validation_alias="curr_id")
    formatted: str | None = None
    value: float | None = None


class ShippingInfo(SDKModel):
    currency: CurrencyCode | str | None = None
    method: str | None = None
    value: float | None = None


class OrderTracking(SDKModel):
    # A tracking object always carries the carrier's number; the rest is optional.
    number: str
    carrier: TrackingCarrier | str | None = None
    url: str | None = None


class OrderRef(SDKModel):
    id: str | None = None
    resource_url: str | None = None


class MessageRefund(SDKModel):
    amount: float | None = None
    order: OrderRef | None = None


class SellerStats(SDKModel):
    rating: str | None = None
    stars: float | None = None
    total: int | None = None


class Seller(UserSummary):
    """Seller profile embedded in a listing: a ``UserSummary`` plus trade details."""

    payment: str | None = None
    shipping: str | None = None
    stats: SellerStats | None = None
    url: str | None = None


class Listing(SDKModel):
    """A Marketplace listing.

    ``external_id``, ``format_quantity``, ``location``, ``quantity`` and
    ``weight`` are returned only to the listing owner, and ``in_cart`` only to
    an authenticated user, so they stay ``None`` for everyone else.
    """

    # Listing detail returns "id"; the creation acknowledgement returns "listing_id".
    id: int = Field(validation_alias=AliasChoices("id", "listing_id"))
    allow_offers: bool | None = None
    audio: bool | None = None
    comments: str | None = None
    condition: Condition | str | None = None
    external_id: str | None = None
    format_quantity: int | None = None
    in_cart: bool | None = None
    location: str | None = None
    original_price: OriginalPrice | None = None
    original_shipping_price: OriginalPrice | None = None
    posted: str | None = None
    price: Price | None = None
    quantity: int | None = None
    release: ListingRelease | None = None
    resource_url: str | None = None
    seller: Seller | None = None
    shipping_price: Price | None = None
    ships_from: str | None = None
    sleeve_condition: SleeveCondition | str | None = None
    status: str | None = None
    uri: str | None = None
    weight: float | None = None


class OrderItem(SDKModel):
    id: int | None = None
    media_condition: Condition | str | None = None
    price: Price | None = None
    release: ListingRelease | None = None
    sleeve_condition: SleeveCondition | str | None = None


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
    tracking: OrderTracking | None = None
    uri: str | None = None


class OrderMessage(SDKModel):
    actor: UserSummary | None = None
    from_user: UserSummary | None = Field(default=None, alias="from")
    message: str | None = None
    # A shipping-change message reports the shipping amount before and after.
    new: float | None = None
    order: OrderRef | None = None
    original: float | None = None
    refund: MessageRefund | None = None
    status_id: int | None = None
    subject: str | None = None
    timestamp: str | None = None
    type: str | None = None


class Fee(SDKModel):
    currency: CurrencyCode | str | None = None
    value: float
