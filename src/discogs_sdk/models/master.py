from __future__ import annotations

from typing import Any

from discogs_sdk.models._common import ArtistCredit, Image, SDKModel, Track, Video


class Master(SDKModel):
    id: int
    artists: list[ArtistCredit] | None = None
    data_quality: str | None = None
    genres: list[str] | None = None
    images: list[Image] | None = None
    lowest_price: float | None = None
    main_release_url: str | None = None
    main_release: int | None = None
    num_for_sale: int | None = None
    resource_url: str | None = None
    styles: list[str] | None = None
    title: str
    tracklist: list[Track] | None = None
    uri: str | None = None
    versions_url: str | None = None
    videos: list[Video] | None = None
    year: int | None = None


class MasterVersion(SDKModel):
    id: int
    catno: str | None = None
    country: str | None = None
    format: str | None = None
    label: str | None = None
    major_formats: list[str] | None = None
    released: str | None = None
    resource_url: str | None = None
    stats: dict[str, Any] | None = None
    status: str | None = None
    thumb: str | None = None
    title: str
