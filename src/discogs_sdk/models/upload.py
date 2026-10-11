from __future__ import annotations

from pydantic import Field

from discogs_sdk.models._common import SDKModel
from discogs_sdk.models._timestamp import Timestamp


class Upload(SDKModel):
    """An inventory upload.

    Discogs sends ``created_ts`` and ``finished_ts`` without an offset
    (``2017-12-18T09:20:28``). ``created_at`` and ``finished_at`` read them as
    ``America/Los_Angeles`` time, an assumption measured against inventory
    exports, and carry the fixed offset in force then. ``raw`` holds the strings
    as sent.
    """

    id: int
    created_at: Timestamp = Field(default=None, validation_alias="created_ts")
    filename: str | None = None
    finished_at: Timestamp = Field(default=None, validation_alias="finished_ts")
    # A completed upload reports a summary string that may contain HTML markup.
    results: str | None = None
    status: str | None = None
    type: str | None = None
