from __future__ import annotations

from pydantic import AliasChoices, Field

from discogs_sdk.models._common import SDKModel
from discogs_sdk.models._timestamp import Timestamp


class ListItem(SDKModel):
    id: int
    comment: str | None = None
    display_title: str | None = None
    image_url: str | None = None
    resource_url: str | None = None
    type: str | None = None
    uri: str | None = None


class List_(SDKModel):
    """A user list with its items.

    ``created_at`` and ``modified_at`` (``created_ts`` and ``modified_ts`` in the
    API) are aware ``datetime`` values parsed from ISO 8601 with an offset;
    ``raw`` holds the strings as sent.
    """

    # The list detail response identifies the list as "list_id".
    id: int = Field(validation_alias=AliasChoices("id", "list_id"))
    created_at: Timestamp = Field(default=None, validation_alias="created_ts")
    description: str | None = None
    items: list[ListItem] | None = None
    modified_at: Timestamp = Field(default=None, validation_alias="modified_ts")
    name: str
    public: bool | None = None
    resource_url: str | None = None
    url: str | None = None


class ListSummary(SDKModel):
    """A list as it appears in a user's lists.

    ``date_added`` and ``date_changed`` are aware ``datetime`` values parsed
    from ISO 8601 with an offset; ``raw`` holds the strings as sent.
    """

    id: int
    date_added: Timestamp = None
    date_changed: Timestamp = None
    description: str | None = None
    name: str
    public: bool | None = None
    resource_url: str | None = None
    uri: str | None = None
