from __future__ import annotations

from typing import Any

from pydantic import Field

from discogs_sdk.models._common import SDKModel


class SearchResult(SDKModel):
    id: int
    barcode: list[str] | None = None
    catalog_number: str | None = Field(default=None, validation_alias="catno")
    community: dict[str, Any] | None = None
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
