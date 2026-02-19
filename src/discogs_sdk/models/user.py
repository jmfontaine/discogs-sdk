from __future__ import annotations

from pydantic import Field

from discogs_sdk.models._common import SDKModel


class Identity(SDKModel):
    id: int
    consumer_name: str | None = None
    resource_url: str | None = None
    username: str


class User(SDKModel):
    id: int
    avatar_url: str | None = None
    banner_url: str | None = None
    buyer_num_ratings: int | None = None
    buyer_rating_stars: float | None = None
    buyer_rating: float | None = None
    collection_fields_url: str | None = None
    collection_folders_url: str | None = None
    currency_code: str | None = Field(default=None, validation_alias="curr_abbr")
    home_page: str | None = None
    inventory_url: str | None = None
    location: str | None = None
    name: str | None = None
    num_collection: int | None = None
    num_for_sale: int | None = None
    num_lists: int | None = None
    num_pending: int | None = None
    num_wantlist: int | None = None
    profile: str | None = None
    rank: int | None = None
    rating_avg: float | None = None
    registered: str | None = None
    releases_contributed: int | None = None
    releases_rated: int | None = None
    resource_url: str | None = None
    seller_num_ratings: int | None = None
    seller_rating_stars: float | None = None
    seller_rating: float | None = None
    uri: str | None = None
    username: str
    wantlist_url: str | None = None
