from __future__ import annotations

from pydantic import Field

from discogs_sdk.models._common import Image, SDKModel, SubLabel


class Label(SDKModel):
    id: int
    contact_info: str | None = None
    data_quality: str | None = None
    images: list[Image] | None = None
    name: str
    profile: str | None = None
    releases_url: str | None = None
    resource_url: str | None = None
    sub_labels: list[SubLabel] | None = Field(default=None, validation_alias="sublabels")
    uri: str | None = None
    urls: list[str] | None = None


class LabelRelease(SDKModel):
    id: int
    artist: str | None = None
    catalog_number: str | None = Field(default=None, validation_alias="catno")
    format: str | None = None
    resource_url: str | None = None
    status: str | None = None
    thumb: str | None = None
    title: str
    year: int | None = None
