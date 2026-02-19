from __future__ import annotations

from pydantic import Field

from discogs_sdk.models._common import Image, Member, SDKModel


class Artist(SDKModel):
    id: int
    data_quality: str | None = None
    images: list[Image] | None = None
    members: list[Member] | None = None
    name_variations: list[str] | None = Field(default=None, validation_alias="namevariations")
    name: str
    profile: str | None = None
    releases_url: str | None = None
    resource_url: str | None = None
    uri: str | None = None
    urls: list[str] | None = None


class ArtistRelease(SDKModel):
    id: int
    artist: str | None = None
    format: str | None = None
    label: str | None = None
    main_release: int | None = None
    resource_url: str | None = None
    role: str | None = None
    status: str | None = None
    thumb: str | None = None
    title: str
    type: str
    year: int | None = None
