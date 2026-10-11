from __future__ import annotations

from pydantic import Field

from discogs_sdk.models._common import SDKModel
from discogs_sdk.models._timestamp import Timestamp


class Export(SDKModel):
    """An inventory export.

    Discogs sends ``created_ts`` and ``finished_ts`` without an offset
    (``2018-09-27T12:59:02``). ``created_at`` and ``finished_at`` read them as
    ``America/Los_Angeles`` time, an assumption measured against the API, and
    carry the fixed offset in force then. ``raw`` holds the strings as sent.
    """

    id: int
    created_at: Timestamp = Field(default=None, validation_alias="created_ts")
    download_url: str | None = None
    filename: str | None = None
    finished_at: Timestamp = Field(default=None, validation_alias="finished_ts")
    status: str | None = None
    url: str | None = None
