from __future__ import annotations

from pydantic import Field

from discogs_sdk.models._common import SDKModel


class ListItem(SDKModel):
    id: int
    comment: str | None = None
    display_title: str | None = None
    image_url: str | None = None
    resource_url: str | None = None
    type: str | None = None
    uri: str | None = None


class List_(SDKModel):
    id: int
    created_at: str | None = Field(default=None, validation_alias="created_ts")
    description: str | None = None
    items: list[ListItem] | None = None
    modified_at: str | None = Field(default=None, validation_alias="modified_ts")
    name: str
    public: bool | None = None
    resource_url: str | None = None
    url: str | None = None


class ListSummary(SDKModel):
    id: int
    date_added: str | None = None
    date_changed: str | None = None
    description: str | None = None
    name: str
    public: bool | None = None
    resource_url: str | None = None
    uri: str | None = None
