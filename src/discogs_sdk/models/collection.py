from __future__ import annotations

from typing import Any

from discogs_sdk.models._common import BasicInformation, SDKModel


class CollectionFolder(SDKModel):
    id: int
    count: int | None = None
    name: str
    resource_url: str | None = None


class CollectionItem(SDKModel):
    id: int
    basic_information: BasicInformation | None = None
    date_added: str | None = None
    folder_id: int | None = None
    instance_id: int | None = None
    notes: list[dict[str, Any]] | None = None
    rating: int | None = None


class CollectionField(SDKModel):
    id: int
    lines: int | None = None
    name: str
    options: list[str] | None = None
    position: int | None = None
    public: bool | None = None
    type: str | None = None


class CollectionValue_(SDKModel):
    maximum: str | None = None
    median: str | None = None
    minimum: str | None = None
