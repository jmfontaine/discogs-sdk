from __future__ import annotations

from pydantic import Field, field_validator

from discogs_sdk.models._common import SDKModel

# Every other entity's ``uri`` is absolute; search results send a site-relative
# path (``/release/352665``) that this host completes.
_SITE_URL = "https://www.discogs.com"


class SearchCommunity(SDKModel):
    have: int | None = None
    want: int | None = None


class SearchResult(SDKModel):
    id: int
    barcode: list[str] | None = None
    catalog_number: str | None = Field(default=None, validation_alias="catno")
    community: SearchCommunity | None = None
    country: str | None = None
    cover_image: str | None = None
    format: list[str] | None = None
    genre: list[str] | None = None
    label: list[str] | None = None
    master_id: int | None = None
    master_url: str | None = None
    resource_url: str | None = None
    style: list[str] | None = None
    thumb: str | None = None
    title: str
    type: str | None = None
    uri: str | None = None
    year: str | None = None

    @field_validator("uri")
    @classmethod
    def _absolute_uri(cls, value: str | None) -> str | None:
        # Prefix the path exactly as sent, percent-encoding included; ``raw``
        # keeps the relative value. An absolute value passes through, so a
        # dumped model validates back unchanged.
        if value is not None and value.startswith("/"):
            return _SITE_URL + value
        return value
