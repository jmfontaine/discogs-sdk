from __future__ import annotations

from pydantic import Field

from discogs_sdk.models._common import (
    ArtistCredit,
    Community,
    Company,
    Format,
    Identifier,
    Image,
    LabelCredit,
    Price,
    SDKModel,
    Track,
    Video,
)


class Release(SDKModel):
    id: int
    artists: list[ArtistCredit] | None = None
    community: Community | None = None
    companies: list[Company] | None = None
    country: str | None = None
    data_quality: str | None = None
    date_added: str | None = None
    date_changed: str | None = None
    estimated_weight: int | None = None
    extra_artists: list[ArtistCredit] | None = Field(default=None, validation_alias="extraartists")
    format_quantity: int | None = None
    formats: list[Format] | None = None
    genres: list[str] | None = None
    identifiers: list[Identifier] | None = None
    images: list[Image] | None = None
    labels: list[LabelCredit] | None = None
    lowest_price: float | None = None
    master_id: int | None = None
    master_url: str | None = None
    notes: str | None = None
    num_for_sale: int | None = None
    released_formatted: str | None = None
    released: str | None = None
    resource_url: str | None = None
    series: list[LabelCredit] | None = None
    status: str | None = None
    styles: list[str] | None = None
    thumb: str | None = None
    title: str
    tracklist: list[Track] | None = None
    uri: str | None = None
    videos: list[Video] | None = None
    year: int | None = None


class RatingInfo(SDKModel):
    average: float
    count: int


class CommunityRating(SDKModel):
    rating: RatingInfo
    release_id: int


class UserReleaseRating(SDKModel):
    rating: int
    release_id: int
    username: str


class ReleaseStats(SDKModel):
    num_have: int | None = None
    num_want: int | None = None


class PriceSuggestions(SDKModel):
    # Discogs uses dynamic condition-name keys (e.g. "Mint (M)", "Very Good Plus (VG+)").
    # extra="allow" captures them; the properties below provide typed access.

    @property
    def conditions(self) -> dict[str, Price]:
        return {k: Price.model_validate(v) for k, v in (self.model_extra or {}).items()}

    def __getitem__(self, condition: str) -> Price:
        extras = self.model_extra or {}
        if condition not in extras:
            raise KeyError(condition)
        return Price.model_validate(extras[condition])


class MarketplaceReleaseStats(SDKModel):
    lowest_price: Price | None = None
    num_for_sale: int | None = None
